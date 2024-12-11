from io import BytesIO
from os.path import dirname, join
from random import choice
from re import compile
from tomllib import loads
from typing import List, Optional, Tuple, Union

from httpx import AsyncClient
from PIL import Image, ImageDraw
from PIL.ImageFont import truetype
from qrcode import QRCode

from .model import Blog
from .options import Options
from .utils import (
    Align,
    Content,
    endl,
    get_cropped_image,
    get_merged_image,
    get_resized_image,
    paste_image,
    set_image_border,
)

ternary_pattern = compile(r"(<([^=?]+)(?:=([^?]+))?\?([^:]*):([^>]*)>)")

__dir__ = dirname(__file__)
image_doc_path = join(__dir__, "assets", "doc.png")
image_date_path = join(__dir__, "assets", "date.png")
font_HarmonyOS_Sans_Bold = join(__dir__, "assets", "HarmonyOS_Sans_SC_Bold.ttf")
font_HarmonyOS_Sans_SC_Regular_seguisym = join(__dir__, "assets", "HarmonyOS_Sans_SC_Regular+seguisym.ttf")


class MyContent(Content):
    """
    类 `Content` 的具体实现
    """

    session = AsyncClient()

    @classmethod
    async def get_emoji(cls, emoji: str) -> Union[str, Image.Image, None]:
        if len(emoji) == 2:
            resp = await cls.session.get("https://www.emojiall.com/images/120/huawei/%x%x.png" % (ord(emoji[0]), ord(emoji[1])))
            if resp.status_code == 200:
                return Image.open(BytesIO(resp.content))
            emoji = emoji[0]  # goto "len(emoji) == 1" and try again

        if len(emoji) == 1:
            resp = await cls.session.get("https://www.emojiall.com/images/120/huawei/%x.png" % ord(emoji))
            if resp.status_code == 200:
                return Image.open(BytesIO(resp.content))

        return emoji

    @classmethod
    async def get_image(cls, url: str) -> Union[str, Image.Image, None]:
        resp = await cls.session.get(url)
        if resp.status_code != 200:
            return None
        if not resp.headers["Content-Type"].startswith("image"):
            return None
        return Image.open(BytesIO(resp.content))


def replace_ternary_operator(text: str, obj: object) -> str:
    """
    替换三目运算符

    Args:
        text (str): 运算符文本
        obj (object): 判断时用到的对象

    Returns:
        替换后文本
    """
    results: List[Tuple[str, str, str, str, str]] = ternary_pattern.findall(text)
    for result in results:
        idx = obj
        original, condition, judgment_value, true_value, false_value = result
        while condition:
            if "." in condition:
                key, condition = condition.split(".", 1)
            else:
                key, condition = condition, ""
            try:
                if isinstance(idx, dict):
                    idx = idx.__getitem__(key)
                elif isinstance(idx, list):
                    idx = idx.__getitem__(int(key))
                else:
                    idx = idx.__getattribute__(key)
            except:
                idx = None
                break
        if idx is None:
            continue
        elif not judgment_value:
            if idx:
                repl = true_value
            else:
                repl = false_value
        elif str(idx) == judgment_value:
            repl = true_value
        else:
            repl = false_value
        text = text.replace(original, repl, 1)
    return text


def format_option(option: Optional[str], blog: Blog) -> str:
    if not isinstance(option, str):
        return "None"
    if "{" not in option:
        return option
    try:
        return option.format(blog)
    except:
        return option


def generate_contents_image_v0(contents: List[Content], width: int = 1000, line_space: int = 0) -> Image.Image:
    """
    生成内容图片

    Args:
        contents (List[Content]): 内容集
        width (int, optional): 图片限宽
        line_space (int, optional): 文字行间距（像素）

    Raises:
        NotImplementedError: 使用了不合规的内容（目前仅支持文字和图片）

    Returns:
        生成的透明底的内容图片
    """
    if len(contents) == 0:
        return Image.new("RGBA", (width, 0))
    prefix = 0
    lines: List[List[Content]] = [[]]
    for content in contents:
        if isinstance(content.value, str):
            while True:
                content_width, _ = content.size
                if prefix + content_width < width:
                    lines[-1].append(content)
                    prefix += content_width
                    break
                elif prefix + content_width == width:
                    lines[-1].append(content)
                    lines.append([])
                    prefix = 0
                    break
                else:
                    for i in range(len(content.value)):
                        content_width = content.font.getlength(content.value[: i + 1])
                        if prefix + content_width < width:
                            continue
                        elif prefix + content_width == width:
                            need, content = content.split(i + 1)
                        else:
                            need, content = content.split(i)
                        lines[-1].append(need)
                        lines.append([])
                        prefix = 0
                        break
        elif isinstance(content.value, Image.Image):
            if content.scale is not None and content.scale < 0:  # 特殊的负值，说明这里希望以总宽度作为参考值
                content.scale = (-content.scale) * width * content.value.height / content.value.width / content.font.size
            content_width, _ = content.size
            if prefix + content_width < width:  # 没超限宽 加偏移量
                lines[-1].append(content)
                prefix += content_width
            elif prefix + content_width == width:  # 正好限宽 加一行
                lines[-1].append(content)
                lines.append([])
                prefix = 0
            elif content_width < width:  # 超了限宽 但是图片本身宽度在限宽内 直接放在下一行
                lines.append([content])
                prefix = content_width
            else:  # 超了限宽
                if content_width > width:  # 本身宽度就超了 先改尺寸
                    content.scale = width * content.value.height / content.value.width / content.font.size
                lines.append([content])
                lines.append([])
                prefix = 0
        elif isinstance(content.value, endl):
            if len(lines[-1]) == 0:
                lines[-1].append(content)
            lines.append([])
            prefix = 0
        else:
            raise NotImplementedError

    if len(lines[-1]) == 0:
        lines.pop()

    contents_height = -line_space
    lines_info: List[Tuple[List[Content], int, int]] = []
    for line in lines:
        ascent, descent, image_height = 0, 0, 0
        for content in line:
            if isinstance(content.value, str):
                baseline, _ = content.font.getmetrics()
                _, top, _, bottom = content.font.getbbox(content.value)
                ascent = max(ascent, baseline - top)
                descent = max(descent, bottom - baseline)
            elif isinstance(content.value, Image.Image):
                image_height = max(image_height, content.size[1])
            elif isinstance(content.value, endl):
                ascent = max(ascent, content.size[1])
            else:
                raise NotImplementedError
        line_height = max(ascent + descent, image_height)
        contents_height += line_height + line_space
        lines_info.append((line, line_height, descent))

    image_contents = Image.new("RGBA", (width, contents_height))
    draw = ImageDraw.ImageDraw(image_contents)

    offset_y = 0
    for line, line_height, descent in lines_info:
        offset_x = 0
        offset_y += line_height
        baseline = offset_y - descent
        for content in line:
            content_width, content_height = content.size
            if isinstance(content.value, Image.Image):
                paste_image(image_contents, content.image, (offset_x, offset_y - content_height))
            elif isinstance(content.value, (str, endl)):
                box = Align.BASELINE((offset_x, baseline), str(content.value), content.font)
                draw.text(box, str(content.value), content.color, content.font)
            else:
                raise NotImplementedError
            offset_x += content_width
        offset_y += line_space

    return image_contents


def generate_contents_image(
    contents: List[Content],
    width: int = 1000,
    line_space: int = 0,
    icon: Optional[Image.Image] = None,
    icon_space: int = 0,
    icon_align: str = "mtm",  # 什么睦头人🥒
) -> Image.Image:
    """
    生成带图标的内容图片

    Args:
        contents (List[Content]): 内容集
        width (int, optional): 图片限宽
        line_space (int, optional): 文字行间距（像素）
        icon (Optional[Image.Image], optional): 图标
        icon_space (int, optional): 图标与文字间距（像素）
        icon_align (str, optional): 图标与文字对齐方式

    Raises:
        NotImplementedError: 使用了不合规的内容（目前仅支持文字和图片）

    Returns:
        生成的透明底的带图标的内容图片
    """
    # 判断 icon_align 是否合规
    if len(icon_align) != 3 or icon_align[0] not in "tmb" or icon_align[1] != "t" or icon_align[2] not in "tmb":
        raise NotImplementedError
    # 没有内容直接返回个空的 有图标加图标
    if len(contents) == 0:
        if isinstance(icon, Image.Image):
            bg = Image.new("RGBA", (width, icon.height))
            paste_image(bg, icon, (0, 0))
            return bg
        else:
            return Image.new("RGBA", (width, 0))
    # 内容区宽度
    contents_width = width - icon_space
    if isinstance(icon, Image.Image):
        contents_width -= icon.width
    # 分割内容为行
    prefix = 0
    lines: List[List[Content]] = [[]]
    for content in contents:
        if isinstance(content.value, str):
            while True:
                text_width, _ = content.size
                if prefix + text_width < contents_width:
                    lines[-1].append(content)
                    prefix += text_width
                    break
                elif prefix + text_width == contents_width:
                    lines[-1].append(content)
                    lines.append([])
                    prefix = 0
                    break
                else:
                    for i in range(len(content.value)):
                        text_width = content.font.getlength(content.value[: i + 1])
                        if prefix + text_width < contents_width:
                            continue
                        elif prefix + text_width == contents_width:
                            need, content = content.split(i + 1)
                        else:
                            need, content = content.split(i)
                        lines[-1].append(need)
                        lines.append([])
                        prefix = 0
                        break
        elif isinstance(content.value, Image.Image):
            if content.scale is not None and content.scale < 0:  # 特殊的负值，说明这里希望以总宽度作为参考值
                content.scale = (-content.scale) * contents_width * content.value.height / content.value.width / content.font.size
            image_width, _ = content.size
            if prefix + image_width < contents_width:  # 没超限宽 加偏移量
                lines[-1].append(content)
                prefix += image_width
            elif prefix + image_width == contents_width:  # 正好限宽 加一行
                lines[-1].append(content)
                lines.append([])
                prefix = 0
            elif image_width < contents_width:  # 超了限宽 但是图片本身宽度在限宽内 直接放在下一行
                lines.append([content])
                prefix = image_width
            else:  # 超了限宽
                if image_width > contents_width:  # 本身宽度就超了 先改尺寸
                    content.scale = contents_width * content.value.height / content.value.width / content.font.size
                lines.append([content])
                lines.append([])
                prefix = 0
        elif isinstance(content.value, endl):
            if len(lines[-1]) == 0:
                lines[-1].append(content)
            lines.append([])
            prefix = 0
        else:
            raise NotImplementedError
    # 去空
    if len(lines[-1]) == 0:
        lines.pop()
    # 计算行高
    contents_height = -line_space
    lines_info: List[Tuple[List[Content], int, int]] = []
    for line in lines:
        ascent, descent, image_height = 0, 0, 0
        for content in line:
            if isinstance(content.value, str):
                baseline, _ = content.font.getmetrics()
                _, top, _, bottom = content.font.getbbox(content.value)
                ascent = max(ascent, baseline - top)
                descent = max(descent, bottom - baseline)
            elif isinstance(content.value, Image.Image):
                image_height = max(image_height, content.size[1])
            elif isinstance(content.value, endl):
                ascent = max(ascent, content.size[1])
            else:
                raise NotImplementedError
        line_height = max(ascent + descent, image_height)
        contents_height += line_height + line_space
        lines_info.append((line, line_height, descent))
    # 确定最终图片高度
    icon_index = 0
    if isinstance(icon, Image.Image):
        if icon_align[0] == "m":
            icon_index = icon.height // 2
        elif icon_align[0] == "b":
            icon_index = icon.height
    content_index = 0
    if icon_align[2] == "m":
        content_index = lines_info[0][1] // 2
    elif icon_align[2] == "b":
        content_index = lines_info[0][1]
    diff = icon_index - content_index
    # 新建空白背景
    contents_height += max(0, diff)
    if isinstance(icon, Image.Image):
        contents_height = max(contents_height, icon.height)
    image_contents = Image.new("RGBA", (width, contents_height))
    # 先贴图标
    if isinstance(icon, Image.Image):
        paste_image(image_contents, icon, (0, max(0, -diff)))
    # 再写文字
    draw = ImageDraw.ImageDraw(image_contents)
    offset_y = max(diff, 0)
    for line, line_height, descent in lines_info:
        offset_x = width - contents_width
        offset_y += line_height
        baseline = offset_y - descent
        for content in line:
            content_width, content_height = content.size
            if isinstance(content.value, Image.Image):
                paste_image(image_contents, content.image, (offset_x, offset_y - content_height))
            elif isinstance(content.value, (str, endl)):
                box = Align.BASELINE((offset_x, baseline), str(content.value), content.font)
                draw.text(box, str(content.value), content.color, content.font)
            else:
                raise NotImplementedError
            offset_x += content_width
        offset_y += line_space
    return image_contents


async def generate_blog_image(
    blog: Blog,
    width: Optional[int] = None,
    max_width: Optional[int] = None,
    cls: Optional[type[Content]] = None,
    options: Optional[Options] = None,
) -> Image.Image:
    """
    根据博文生成图片

    Args:
        blog (Blog): 博文
        width (Optional[int]): 成图宽度
        max_width (Optional[int]): 成图限制宽度

    Returns:
        成图
    """
    # 初始化内容类
    if cls is None:
        cls = MyContent
    # 加载配置选项
    if options is None:
        if blog.extra is not None:
            generate_options = blog.extra.get("generate_options")
            if generate_options is not None:
                options = Options.model_validate(loads(generate_options))
    if options is None:
        options = Options()
    # 计算成图宽度
    if width is None:
        width = options.width
    if max_width is not None:
        width = min(width, max_width)
    width = int(width)
    # 加载特别好看的鸿蒙字体
    font_size = int(0.035 * width)
    font_bold = truetype(font_HarmonyOS_Sans_Bold, font_size)
    font_regular = truetype(font_HarmonyOS_Sans_SC_Regular_seguisym, font_size)
    # 获取头像
    if options.avatar.enable:
        image_avatar = None
        if blog.avatar is not None and blog.avatar != "":
            image_avatar = await cls.get_image(blog.avatar)
        # 不存在链接或获取失败则使用纯色头像
        if not isinstance(image_avatar, Image.Image):
            image_avatar = Image.new("RGBA", (400, 400), "#eeeeee")
        # 处理头像 先裁剪成正方形 再加上描边圆角 注意这里不能改顺序不然边框宽度计算会出问题
        image_avatar = get_cropped_image(image_avatar, 1)
        image_avatar = set_image_border(
            image_avatar,
            radius=options.avatar.border.radius,
            width=f"{int(options.avatar.border.width * image_avatar.width)}px",
            color=options.avatar.border.color,
            scale=3,
        )
        # 缩放头像
        image_avatar = get_resized_image(image_avatar, width=int(options.avatar.width * width))
    # 计算头像的位置偏移量 这是一个下文反复要用到的尺寸 即使不显示头像
    avatar_width = int(options.avatar.width * width)  # == avatar_height
    avatar_x = int(options.avatar.offset * avatar_width)
    # 用户信息模块（高度计算 = 剩余头像高度 + 间距 + 字高 + 间距 + 字高 + 间距 + 间距，间距 = 头像偏移量一半）
    user_info_height = avatar_width - avatar_x + avatar_x
    if options.description.enable and not options.description.hoisting:
        user_info_height += int(options.description.size * width) + avatar_x // 2
    if options.time.enable and not options.time.hoisting:
        user_info_height += int(options.time.size * width) + avatar_x // 2
    # 模块左右上角圆角
    radius_user_info = min(int(options.banner.radius * width), user_info_height)
    user_info = Image.new("RGB", (width, user_info_height), options.color)
    user_info = set_image_border(user_info, radius=f"{radius_user_info}px {radius_user_info}px 0px 0px", scale=3)
    draw_user_info = ImageDraw.ImageDraw(user_info)
    # 用户名
    if blog.name is None or blog.name == "":
        name = "用户"
    else:
        name = blog.name
    font_name = font_bold.font_variant(size=options.name.size * width)
    name_left, name_top, name_right, name_bottom = font_name.getbbox(name)
    name_width, name_height = name_right - name_left, name_bottom - name_top
    # 用户名偏移
    if options.avatar.enable:
        name_x = avatar_width + 2 * avatar_x  # 头像宽度加上两个头像偏移量 可以把头像放在一个居中的位置 好看
    else:
        name_x = avatar_x
    name_y = avatar_width // 2 - avatar_x - name_height // 2
    draw_user_info.text((name_x - name_left, name_y - name_top), name, options.name.color, font_name)
    # 用户 ID 与用户名基线对齐
    if options.uid.enable and blog.uid is not None and blog.uid != "":
        uid_x = name_x + name_width
        uid_y = name_y + font_name.getmetrics()[0] - font_regular.getmetrics()[0]
        font_uid = font_regular.font_variant(size=options.uid.size * width)
        draw_user_info.text((uid_x, uid_y), options.uid.prefix + blog.uid, options.uid.color, font_uid)
    # 第二行文字位置的确定
    _, info_top, _, info_bottom = font_bold.getbbox("粉丝关注")
    info_y = name_y + name_height + (info_bottom - info_top) // 2  # 1.5 倍行距
    # 自定义第二行文字
    if options.follow.enable and not options.description.hoisting and not options.time.hoisting:
        font_bold_follow = font_bold.font_variant(size=options.follow.size * width)
        font_regular_follow = font_regular.font_variant(size=options.follow.size * width)
        contents = []
        for i, text in enumerate(options.follow.text):

            text = format_option(replace_ternary_operator(text, blog), blog)
            if text == "":
                continue
            if i & 1 == 0:
                contents.append(Content(text, font_bold_follow, options.follow.color_primary))
            else:
                contents.append(Content(text, font_regular_follow, options.follow.color_secondary))
        image_follow = generate_contents_image(contents, width=width - name_x - avatar_x)
        user_info.paste(image_follow, (name_x, info_y))
    # 简介图标
    font_size_desc = int(options.description.size * width)
    image_doc = get_resized_image(Image.open(image_doc_path), height=font_size_desc)
    doc_y = avatar_width - avatar_x // 2
    if options.description.enable:
        if options.description.hoisting:
            doc_x_v2, doc_y_v2 = name_x, info_y
        else:
            doc_x_v2, doc_y_v2 = avatar_x, doc_y
        if options.description.icon:
            user_info.paste(image_doc, (doc_x_v2, doc_y_v2), image_doc)
            doc_x_v2 += int(1.5 * image_doc.width)
        # 简介文字
        if blog.description is None or blog.description == "":
            description = "暂无简介"
        else:
            description = blog.description
        font_regular_desc = font_regular.font_variant(size=font_size_desc)
        _, desc_top, _, desc_bottom = font_regular_desc.getbbox(description)
        desc_y = doc_y_v2 - desc_top + (image_doc.height - desc_bottom + desc_top) // 2  # 居中对齐
        draw_user_info.text((doc_x_v2, desc_y), description, options.description.color, font_regular_desc)
    # 时间
    if options.time.enable:
        # 时间图标 与简介图标同宽
        image_date = get_resized_image(Image.open(image_date_path), width=image_doc.width)
        if options.time.hoisting:
            date_x, date_y = name_x, info_y
        else:
            date_x, date_y = avatar_x, doc_y
            if options.description.enable and not options.description.hoisting:
                date_y += image_date.height + avatar_x // 2
        if options.time.icon:
            user_info.paste(image_date, (date_x, date_y), image_date)
            date_x += int(1.5 * image_date.width)
        # 时间文字
        time_str = ""
        if blog.time is not None:
            time_str = blog.time.strftime("%Y/%m/%d %H:%M:%S ")
        if blog.source is not None and blog.source != "":
            time_str += blog.source
        if time_str == "":
            time_str = "暂无时间"
        # 写时间
        font_size_date = int(options.time.size * width)
        font_regular_date = font_regular.font_variant(size=font_size_date)
        time_left, time_top, _, time_bottom = font_regular_date.getbbox(time_str)
        time_y = date_y - time_top + (image_date.height - time_bottom + time_top) // 2  # 居中对齐
        draw_user_info.text((date_x - time_left, time_y), time_str, options.time.color, font_regular_date)
    # 背景图
    if options.banner.enable:
        if options.banner.image.enable and blog.banner is not None:
            idx = options.banner.image.index
            if 0 <= idx < len(blog.banner):
                banner_url = blog.banner[idx]
            else:
                banner_url = choice(blog.banner)
            image_banner = await cls.get_image(banner_url)
            if isinstance(image_banner, Image.Image):
                image_banner = get_cropped_image(image_banner, options.banner.image.ratio, options.banner.image.offset)
                image_banner = get_resized_image(image_banner, width=width)
            else:
                image_banner = Image.new("RGB", (width, banner_height), options.banner.color)
        else:
            banner_height = avatar_x
            if options.avatar.enable:
                banner_height += avatar_x + radius_user_info
            image_banner = Image.new("RGB", (width, banner_height), options.banner.color)
    else:
        banner_height = avatar_x
        if options.avatar.enable:
            banner_height += avatar_x + radius_user_info
        image_banner = Image.new("RGB", (width, banner_height), options.color)
    # 内容
    if options.content.enable and blog.text is not None and blog.text != "":
        width_text = truetype(font_HarmonyOS_Sans_SC_Regular_seguisym, 100).getlength(options.content.size)
        font_text = truetype(font_HarmonyOS_Sans_SC_Regular_seguisym, int(100 * (width - 2 * avatar_x) / width_text))
        contents = await cls.from_html(blog.text.strip(), options.content.color_primary, options.content.color_secondary)
        for content in contents:
            content.font = font_text
            print(content)
        box_space = font_text.getbbox("中嘞")

        image_content = generate_contents_image(contents, width=width - 2 * avatar_x, line_space=(box_space[3] - box_space[1]) // 2)
    else:
        image_content = None
    # 转发
    if options.reply.enable and blog.reply is not None:
        # 传递配置选项
        if options.reply.options != "":
            reply_options = Options.model_validate(loads(options.reply.options))
        else:
            reply_options = options
        # 生成转发的博文图片
        image_reply = await generate_blog_image(
            blog.reply,
            width=width - 2 * avatar_x - 2 * options.reply.width,
            cls=cls,
            options=reply_options,
        )
        # 加圆角和描边
        radius_reply = min(int(options.reply.radius * width), image_reply.height // 2)
        image_reply = set_image_border(
            image_reply,
            radius=f"{radius_reply}px",
            width=f"{options.reply.width}px",
            color=options.reply.color,
            scale=3,
        )
    else:
        image_reply = None
    # 配图
    images: List[Image.Image] = []
    images_height = 0
    if options.images.enable and blog.assets is not None:
        for assets in blog.assets:
            img = await cls.get_image(assets)
            if isinstance(img, Image.Image):
                img = get_resized_image(img, width=width)
                images_height += img.height
                images.append(img)
    # 高度太高 改成九宫格模式
    if images_height > options.images.max_height * width:
        if options.images.merge.enable:
            im = get_merged_image(
                images,
                max_width=width - 2 * avatar_x,
                space=options.images.merge.space,
                radius=options.images.merge.radius,
                number_per_row=options.images.merge.number_per_row,
                max_number_per_row=options.images.merge.max_number_per_row,
            )
            images = [im]
            images_height = im.height + avatar_x // 2
        else:
            images = []
            images_height = 0
    # 页脚二维码
    if options.footer.enable:
        if blog.url is None:
            blog.url = ""
        text_primary = format_option(options.footer.text_primary, blog)
        text_secondary = format_option(options.footer.text_secondary, blog)
        _, text_top, _, text_bottom = font_bold.getbbox(text_primary)
        _, url_top, _, url_bottom = font_regular.getbbox(text_secondary)
        image_footer = Image.new("RGB", (width, 2 * avatar_x + int(1.2 * (text_bottom - text_top) + url_bottom - url_top)), options.footer.color_background)
        draw_footer = ImageDraw.ImageDraw(image_footer)
        draw_footer.text((avatar_x, avatar_x), text_primary, options.footer.color_primary, font_bold)
        draw_footer.text((avatar_x, avatar_x + int(1.2 * (text_bottom - text_top))), text_secondary, options.footer.color_secondary, font_regular)

        if options.footer.qrcode.enable:
            if options.footer.qrcode.url != "":
                image_url = await cls.get_image(options.footer.qrcode.url)
                if isinstance(image_url, Image.Image):
                    image_url = get_resized_image(image_url, height=image_footer.height - avatar_x)
                    paste_image(image_footer, image_url, (image_footer.width - image_url.width - avatar_x // 2, avatar_x // 2))
            else:
                qr = QRCode(border=0)
                qr.add_data(blog.url)
                image_qrcode = qr.make_image(fill_color=options.footer.qrcode.color_primary, back_color=options.footer.qrcode.color_secondary).get_image()
                image_qrcode = get_resized_image(image_qrcode, height=image_footer.height - avatar_x)
                image_footer.paste(image_qrcode, (image_footer.width - image_qrcode.width - avatar_x // 2, avatar_x // 2))
    else:
        image_footer = None
    # 最底图层
    bg_height = image_banner.height + user_info.height - radius_user_info + images_height
    if image_content is not None:
        bg_height += image_content.height + avatar_x
    if image_reply is not None:
        bg_height += image_reply.height + avatar_x
    if image_footer is not None:
        bg_height += image_footer.height
    bg = Image.new("RGB", (width, bg_height), options.color)
    # 背景图
    bg.paste(image_banner, (0, 0))
    # 信息模块
    bg_offset_y = image_banner.height - radius_user_info
    bg.paste(user_info, (0, bg_offset_y), user_info)
    # 头像
    if options.avatar.enable:
        bg.paste(image_avatar, (avatar_x, bg_offset_y - avatar_x), image_avatar)
    bg_offset_y += user_info.height
    # 内容
    if image_content is not None:
        bg.paste(image_content, (avatar_x, bg_offset_y), image_content)
        bg_offset_y += image_content.height + avatar_x
    # 转发
    if image_reply is not None:
        bg.paste(image_reply, (avatar_x, bg_offset_y), image_reply)
        bg_offset_y += image_reply.height + avatar_x
    # 图片
    for img in images:
        paste_image(bg, img, ((width - img.width) // 2, bg_offset_y))
        bg_offset_y += img.height
    # 页脚
    if image_footer is not None:
        bg.paste(image_footer, (0, bg.height - image_footer.height))
    return bg

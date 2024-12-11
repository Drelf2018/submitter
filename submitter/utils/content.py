from dataclasses import dataclass
from enum import Enum, auto
from io import BytesIO
from re import compile
from typing import List, Optional, Tuple, Union

from emoji import is_emoji
from lxml import etree
from PIL import Image
from PIL.ImageFont import FreeTypeFont

style_height_pattern = compile(r'height *: *([^;"]+)')


class Align(Enum):
    """
    对齐方式
    """

    TOP = auto()
    MIDDLE = auto()
    BASELINE = auto()
    BOTTOM = auto()

    def __call__(self, box: Tuple[int, int], text: str, font: FreeTypeFont) -> Tuple[int, int]:
        """
        根据输入坐标返回相应对齐方式后起始点坐标

        Args:
            box (Tuple[int, int]): 要对其的坐标
            text (str): 要对其的文字
            font (FreeTypeFont): 使用的字体

        Returns:
            对齐后起始点坐标
        """
        left, top, _, bottom = font.getbbox(text)
        if self is Align.TOP:
            return (box[0] - left, box[1] - top)
        elif self is Align.MIDDLE:
            return (box[0] - left, box[1] - (top + bottom) // 2)
        elif self is Align.BASELINE:
            ascent, _ = font.getmetrics()
            return (box[0] - left, box[1] - ascent)
        elif self is Align.BOTTOM:
            return (box[0] - left, box[1] - bottom)
        else:
            raise NotImplementedError


class endl:
    def __str__(self):
        return "\n"


@dataclass
class Content:
    """
    内容类

    须自行实现类方法 `get_emoji` 和 `get_image`
    """

    value: Union[str, Image.Image, endl]  # 按出现频率排序
    font: Optional[FreeTypeFont] = None
    color: Optional[str] = None
    scale: Optional[float] = None

    def __str__(self) -> str:
        return "Content(%r, %s, %s)" % (self.value, self.color, self.scale)

    def __len__(self) -> int:
        if not isinstance(self.value, str):
            return 0
        return len(self.value)

    def __bool__(self) -> bool:
        return self.value is not None

    @property
    def size(self) -> Tuple[int, int]:
        if isinstance(self.value, (str, endl)):
            left, top, right, bottom = self.font.getbbox(str(self.value))
            return (right - left, bottom - top)
        elif isinstance(self.value, Image.Image):
            if self.scale is None:
                return self.value.size
            else:
                height = self.scale * self.font.size
                return (int(self.value.width * height / self.value.height), int(height))
        else:
            raise NotImplementedError

    @property
    def emoji(self) -> Optional[str]:
        if isinstance(self.value, str) and is_emoji(self.value):
            return self.value
        return None

    @property
    def image(self) -> Optional[Image.Image]:
        if not isinstance(self.value, Image.Image):
            return None
        if self.value.size == self.size:
            return self.value
        return self.value.resize(self.size, Image.Resampling.LANCZOS)

    def split(self, idx: int) -> Tuple["Content", "Content"]:
        """
        分割文本内容（未检查边界）

        Returns:
            根据指定索引分割开的两个文本内容，字体与颜色与原先一致
        """
        if not isinstance(self.value, str):
            raise NotImplementedError
        return Content(self.value[:idx], self.font, self.color), Content(self.value[idx:], self.font, self.color)

    def split_by_width(self, max_width: int) -> Tuple["Content", "Content"]:
        """
        根据最大宽度分割文本内容

        Returns:
            根据最大宽度分割开的两个文本内容，字体与颜色与原先一致
        """
        if not isinstance(self.value, str):
            raise NotImplementedError
        left, middle, right = 0, len(self.value), len(self.value)
        while left < right:
            width = self.font.getlength(self.value[:middle])
            if width < max_width:
                left = middle + 1
            elif width == max_width:
                return self.split(middle)
            else:
                right = middle
            middle = (left + right) // 2
        return self.split(left - 1)

    @classmethod
    async def get_emoji(cls, emoji: str) -> Union[str, Image.Image, None]:
        """
        获取文本 `emoji` 代表的图片，如果不希望以图片形式插入 `emoji` 请返回字符串，该字符串会替代原本的 `emoji`（可使用空字符串）

        注意，该文本长度不一定为 `1` 可能为长度为 `2` 的组合 `emoji`

        Args:
            emoji (str): 文本格式 `emoji`

        Returns:
            字符串或者图片格式 `emoji`
        """
        raise NotImplementedError

    @classmethod
    async def get_image(cls, url: str) -> Union[str, Image.Image, None]:
        """
        获取链接代表的图片

        Args:
            url (str): 图片链接

        Returns:
            图片
        """
        raise NotImplementedError

    @classmethod
    async def from_img(cls, node: etree._Element, color: Optional[str] = None, scale: Optional[float] = None) -> List["Content"]:
        """
        从节点为 `img` 的 `etree._Element` 对象中解析出内容集

        Args:
            node (etree._Element): 节点
            color (Optional[str]): 当图片获取失败时，使用标签 `alt` 中文字时用的颜色
            scale (Optional[float]): 图片在正文中的缩放倍数，不提供时会从属性 `scale` 中直接取数，如果值不存在还会尝试从属性 `style` 的 `height` 项中获取

        Returns:
            内容集
        """
        img = await cls.get_image(node.get("src"))
        if img is None:
            alt = node.get("alt")
            if isinstance(alt, str):
                return await cls.from_text(alt, color)
            return []
        elif isinstance(img, str):
            return await cls.from_text(img, color)
        content = Content(img)
        if scale is not None:
            content.scale = scale
        else:
            v = node.get("scale")
            if v is not None:
                content.scale = float(v)
            else:
                style: List[str] = style_height_pattern.findall(node.get("style", ""))
                for height in style:
                    height = height.strip()
                    if height.endswith("rem"):
                        content.scale = float(height[:-3])
                    elif height.endswith("em"):
                        content.scale = float(height[:-2])
        return [content]

    @classmethod
    async def from_text(cls, text: str, color: Optional[str] = None) -> List["Content"]:
        """
        从文本中解析出内容集

        Args:
            text (str): 待解析文本
            color (Optional[str]): 文字颜色

        Returns:
            内容集
        """
        contents = []
        prefix = ""

        def append(value: Union[Image.Image, str, endl], new_color: Optional[str] = None, scale: Optional[float] = None):
            nonlocal prefix
            if prefix != "":
                contents.append(Content(prefix, color=color))
                prefix = ""
            contents.append(Content(value, color=new_color, scale=scale))

        idx = 0
        while idx < len(text):
            if idx + 1 < len(text) and is_emoji(text[idx : idx + 2]):
                emoji = await cls.get_emoji(text[idx : idx + 2])
                # 图片获取成功 把先前的文本存进内容集 并再加上这个图片内容
                if isinstance(emoji, Image.Image):
                    append(emoji, scale=1)
                # 图片获取失败 把这个 emoji 以文本添加 说不定后续使用的字体是含有 emoji 的
                elif isinstance(emoji, str):
                    append(emoji, color=color)
                idx += 2
            elif is_emoji(text[idx]):
                # 逻辑同上
                emoji = await cls.get_emoji(text[idx])
                if isinstance(emoji, Image.Image):
                    append(emoji, scale=1)
                elif isinstance(emoji, str):
                    append(emoji, color=color)
                idx += 1
            elif text[idx] == "\n":
                append(endl())
                idx += 1
            else:
                prefix += text[idx]  # 我都用 Python 了难道在乎这一点“反复新建字符串”的性能开销？
                idx += 1

        if prefix != "":  # 别忘了把 prefix 里残留的文本也加进去
            contents.append(Content(prefix, color=color))
        return contents

    @classmethod
    async def from_html(cls, html: str, color_primary: Optional[str] = None, color_secondary: Optional[str] = None) -> List["Content"]:
        """
        从包含 `html` 代码的文本中解析出内容集

        Args:
            html (str): 待解析文本
            color_primary (Optional[str]): 主要文字颜色
            color_secondary (Optional[str]): 次要文字颜色

        Returns:
            内容集
        """
        contents = []
        html = html.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        div: etree._Element = etree.HTML(f"<div>{html}</div>").xpath("/html/body/div")[0]
        for item in div.xpath("./text() | .//a | .//img[not(ancestor::a)]"):
            if isinstance(item, str):
                contents.extend(await cls.from_text(item, color_primary))
            elif isinstance(item, etree._Element):
                if item.tag == "a":
                    for child in item.xpath(".//img | .//text()"):
                        if isinstance(child, str):
                            contents.extend(await cls.from_text(child, color_secondary))
                        elif isinstance(child, etree._Element):
                            contents.extend(await cls.from_img(child, color_secondary))
                        else:
                            raise NotImplementedError
                elif item.tag == "img":
                    contents.extend(await cls.from_img(item, color_primary))
                else:
                    raise NotImplementedError
            else:
                raise NotImplementedError
        return contents

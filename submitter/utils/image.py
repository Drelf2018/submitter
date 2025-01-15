from math import ceil, sqrt
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw


def split_value(value: str) -> Tuple[str, str, str, str]:
    """
    分割字符串

    Args:
        value (str): 符合 CSS 格式的参数字符串

    Returns:
        符合 CSS 参数补充规则的分割后的字符串元组
    """
    values = tuple(filter(lambda s: s != "", value.strip().split(" ")))
    if len(values) == 1:
        return values[0], values[0], values[0], values[0]
    elif len(values) == 2:
        return values[0], values[1], values[0], values[1]
    elif len(values) == 3:
        return values[0], values[1], values[2], values[1]
    elif len(values) == 4:
        return values


def calc_length(val: str, base_length: float = 0.0, font_size: float = 16) -> float:
    """
    计算字符串表示的具体长度

    目前仅支持 `px` `em` `%` 单位

    Args:
        val (str): 长度字符串
        base_length (float, optional): 使用 `%` 时的参考值
        font_size (float, optional): 使用 `em` 时的参考值

    Returns:
        计算后长度
    """
    if val.endswith("px"):
        return float(val[:-2])
    elif val.endswith("%"):
        return float(val[:-1]) * base_length / 100
    elif val.endswith("rem"):
        return 0.0
    elif val.endswith("em"):
        return float(val[:-2]) * font_size
    else:
        return 0.0


def paste_image(bg: Image.Image, im: Image.Image, box: Tuple[int, int]):
    """
    贴图，有蒙版会自动加

    Args:
        bg (Image.Image): 背景图
        im (Image.Image): 前景图
        box (Tuple[int, int]): 位置
    """
    if im.mode in ("RGBA", "RGBa"):
        bg.paste(im, box, im)
    else:
        bg.paste(im, box)


def get_resized_image(
    im: Image.Image,
    width: Optional[int] = None,
    height: Optional[int] = None,
    resample: Optional[int] = None,
    reducing_gap: Optional[float] = None,
):
    """
    按比例缩放图像，至少设置宽度或高度之一

    Args:
        im (Image.Image): 要缩放的图片
        width (Optional[int]): 新图片宽度
        height (Optional[int]): 新图片高度
        resample (Optional[int]): 同 `Image.Image.resize` 函数
        reducing_gap (Optional[float]): 同 `Image.Image.resize` 函数

    Raises:
        NotImplementedError: `width` `height` 都为 `None` 时的错误

    Returns:
        缩放后图片
    """
    if width is None:
        if height is None:
            raise NotImplementedError
        width = im.width * height / im.height
    else:
        if height is None:
            height = im.height * width / im.width
    if im.size == (int(width), int(height)):
        return im
    return im.resize((int(width), int(height)), resample=resample, reducing_gap=reducing_gap)


def get_rounded_rectangle_alpha(size: Tuple[int, int], radius: Tuple[int, int, int, int, int, int, int, int]) -> Image.Image:
    """
    获取圆角蒙版

    Args:
        size (tuple[int, int] | list[int]): 蒙版长宽
        radius (Tuple[int, int, int, int, int, int, int, int]): 八个圆角半径组成的元组，参数顺序同 CSS 中 border-radius 对顺序的规定

    Returns:
        蒙版图层
    """
    radius = [max(i, 0) for i in radius]
    alpha = Image.new("L", size, "black")
    draw = ImageDraw.ImageDraw(alpha)

    if radius[0] != 0 and radius[4] != 0:
        draw.pieslice([(0, 0), (2 * radius[0] - 1, 2 * radius[4] - 1)], start=180, end=270, fill="white")

    if radius[1] != 0 and radius[5] != 0:
        draw.pieslice([(size[0] - 2 * radius[1], 0), (size[0] - 1, 2 * radius[5] - 1)], start=270, end=0, fill="white")

    if radius[2] != 0 and radius[6] != 0:
        draw.pieslice([(size[0] - 2 * radius[2], size[1] - 2 * radius[6]), (size[0] - 1, size[1] - 1)], start=0, end=90, fill="white")

    if radius[3] != 0 and radius[7] != 0:
        draw.pieslice([(0, size[1] - 2 * radius[7]), (2 * radius[3] - 1, size[1] - 1)], start=90, end=180, fill="white")

    draw.polygon(
        [
            (radius[0], 0),
            (size[0] - 1 - radius[1], 0),
            (size[0] - 1 - radius[1], radius[5]),
            (size[0] - 1, radius[5]),
            (size[0] - 1, size[1] - 1 - radius[6]),
            (size[0] - 1 - radius[2], size[1] - 1 - radius[6]),
            (size[0] - 1 - radius[2], size[1] - 1),
            (radius[3], size[1] - 1),
            (radius[3], size[1] - 1 - radius[7]),
            (0, size[1] - 1 - radius[7]),
            (0, radius[4]),
            (radius[0], radius[4]),
        ],
        fill="white",
    )
    return alpha


def get_cropped_image(im: Image.Image, ratio: float, offset: int = 0) -> Image.Image:
    """
    按比例裁剪图像

    Args:
        im (Image.Image): 要裁剪的图片
        ratio (float): 长宽比 例如：想要裁剪出 16:9 的图片，传入 16/9 即可
        offset (int): 裁剪时的偏移量，例如将一张横向图片裁剪至 `1:1` 时传入 `offset=-100` 会裁剪出中间偏左 `100` 像素的区域（未检查是否超出边界）

    Returns:
        裁剪后图片
    """
    w, h = im.size
    r = w - ratio * h
    if r == 0:
        return im
    elif r > 0:  # 过宽
        return im.crop((r // 2 + offset, 0, r // 2 + ratio * h + offset, h))
    else:  # 过高
        new_height = int(w / ratio)
        top = (h - new_height) // 2
        return im.crop((0, top + offset, w, top + new_height + offset))


def get_merged_image(
    images: List[Image.Image],
    max_width: int,
    space: Optional[int] = None,
    radius: Optional[str] = None,
    number_per_row: Optional[int] = None,
    max_number_per_row: int = 3,
) -> Image.Image:
    """
    拼接图像

    Args:
        images (List[Image.Image]): 图像集
        max_width (int): 拼接后图像的最大宽度
        space (Optional[int]): 图片间距
        radius (Optional[str]): 图片圆角半径，参数格式同 `set_image_border` 函数
        number_per_row (Optional[int]): 每行图片张数，不设置会根据公式计算
        max_number_per_row (int, optional): 未设置 `number_per_row` 时生效，根据公式计算后不超过该数，默认 `3`

    Returns:
        拼接后图像
    """
    # 数量计算
    if number_per_row is None or number_per_row <= 0:
        number_per_row = min(max_number_per_row, ceil(sqrt(len(images))))
    number_per_row = int(number_per_row)
    number_of_rows = ceil(len(images) / number_per_row)
    # 尺寸计算
    space = round(space) if space is not None else round(0.01 * max_width)
    width = (max_width - (number_per_row - 1) * space) // number_per_row
    bg_width = number_per_row * width + (number_per_row - 1) * space
    bg_height = number_of_rows * width + (number_of_rows - 1) * space
    # 定位图片
    bg = Image.new("RGBA", (bg_width, bg_height))
    for idx in range(len(images)):
        img = get_cropped_image(images[idx], 1)
        img = set_image_border(img, radius=radius)
        img = get_resized_image(img, width=width)
        paste_image(bg, img, ((idx % number_per_row) * (width + space), (idx // number_per_row) * (width + space)))
    return bg


def set_image_border(
    image: Image.Image,
    radius: Optional[str] = None,
    width: Optional[str] = None,
    color: Optional[str] = None,
    scale: int = 1,
) -> Image.Image:
    """
    为图片设置边框

    特殊的，参数 `scale` 为缩放参数，因为处理圆角时会因为精度问题出现锯齿，但是先把图片放大，处理完成后再缩小回来就能减少锯齿。

    该参数默认值为 `1` 即不进行缩放，若希望通过上述方法减小锯齿，设置一个大于 `1` 的数值即可。

    但是，使用该参数后会导致圆角模糊、颜色偏差（因为使用了插值缩放）等问题，请谨慎使用。

    Args:
        image (Image.Image): 要设置边框的图片
        radius (Optional[str]): 边框圆角，格式同 CSS
        width (Optional[str]): 边框宽度，格式同 CSS
        color (Optional[str]): 边框颜色，格式同 CSS
        scale (int, optional): 缩放参数

    Returns:
        设置边框后的图片
    """
    if scale != 1:
        image = get_resized_image(image, width=scale * image.width)

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    if width is None:
        new_width, new_height = image.size
    else:
        width_top, width_right, width_bottom, width_left = split_value(width)

        width_top = int(calc_length(width_top) * scale)
        width_right = int(calc_length(width_right) * scale)
        width_bottom = int(calc_length(width_bottom) * scale)
        width_left = int(calc_length(width_left) * scale)

        new_width = image.width + width_left + width_right
        new_height = image.height + width_top + width_bottom

        border = Image.new("RGBA", (new_width, new_height))
        draw = ImageDraw.ImageDraw(border)

        if color is None:
            color_top = color_right = color_bottom = color_left = None
        else:
            color_top, color_right, color_bottom, color_left = split_value(color)

        # 左上第一次着色
        half_y = width_top - 1 + image.height // 2
        half_x = width_left - 1 + image.width // 2
        draw.rectangle(
            [
                (width_left, 0),
                (new_width - 1, half_y),
            ],
            fill=color_top,
        )
        # 右上着色
        if width_right > 0:
            if width_top <= 0:
                draw.polygon(
                    [
                        (new_width - 1, 0),
                        (half_x + 1, 0),
                        (half_x + 1, new_height - 1),
                        (new_width - 1, new_height - 1),
                    ],
                    fill=color_right,
                )
            else:
                x = half_x + 1
                y = half_y
                if width_top != 1:
                    u = new_width + (1 - width_right) * y / (width_top - 1) - 1
                    if u >= x:
                        x = u
                    else:
                        y = (width_top - 1) * (x - new_width + 1) / (1 - width_right)
                draw.polygon(
                    [
                        (new_width - 1, 0),
                        (width_left + image.width, width_top - 1),
                        (x, y),
                        (x, new_height - 1),
                        (new_width - 1, new_height - 1),
                    ],
                    fill=color_right,
                )
        # 右下着色
        if width_bottom > 0:
            if width_right <= 0:
                draw.polygon(
                    [
                        (new_width - 1, new_height - 1),
                        (new_width - 1, half_y + 1),
                        (0, half_y + 1),
                        (0, new_height - 1),
                    ],
                    fill=color_bottom,
                )
            else:
                x = half_x + 1
                y = half_y + 1
                if width_right != 1:
                    u = width_left + image.width + (1 - width_right) * (y - width_top - image.height) / (1 - width_bottom)
                    if u >= x:
                        x = u
                    else:
                        y = width_top + image.height + (1 - width_bottom) * (x - width_left - image.width) / (1 - width_right)
                draw.polygon(
                    [
                        (new_width - 1, new_height - 1),
                        (width_left + image.width, width_top + image.height),
                        (x, y),
                        (0, y),
                        (0, new_height - 1),
                    ],
                    fill=color_bottom,
                )
        # 左下着色
        if width_left > 0:
            if width_bottom <= 0:
                draw.polygon(
                    [
                        (0, new_height - 1),
                        (half_x, new_height - 1),
                        (half_x, 0),
                        (0, 0),
                    ],
                    fill=color_left,
                )
            else:
                x = half_x
                y = half_y + 1
                if width_bottom != 1:
                    u = width_left - 1 + (width_left - 1) * (y - width_top - image.height) / (1 - width_bottom)
                    if u <= x:
                        x = u
                    else:
                        y = width_top + image.height + (1 - width_bottom) * (x - width_left + 1) / (width_left - 1)
                    draw.polygon(
                        [
                            (0, new_height - 1),
                            (width_left - 1, width_top + image.height),
                            (x, y),
                            (x, 0),
                            (0, 0),
                        ],
                        fill=color_left,
                    )
        # 左上第二次着色
        if width_top > 0:
            if width_left <= 0:
                draw.polygon(
                    [
                        (0, 0),
                        (0, half_y),
                        (half_x, half_y),
                        (half_x, 0),
                    ],
                    fill=color_top,
                )
            else:
                x = half_x
                y = half_y
                if width_left != 1:
                    u = width_left - 1 + (width_left - 1) * (y - width_top + 1) / (width_top - 1)
                    if u <= x:
                        x = u
                    else:
                        y = width_top - 1 + (width_top - 1) * (x - width_left + 1) / (width_left - 1)
                    draw.polygon(
                        [
                            (0, 0),
                            (width_left - 1, width_top - 1),
                            (x, y),
                            (half_x, half_y),
                            (half_x, 0),
                        ],
                        fill=color_top,
                    )

    if radius is not None:
        radius_values = []

        if "/" in radius:
            radius_horizontal, radius_vertical = radius.split("/")
        else:
            radius_horizontal = radius_vertical = radius

        for r in split_value(radius_horizontal):
            radius_values.append(calc_length(r, new_width / scale) * scale)
        for r in split_value(radius_vertical):
            radius_values.append(calc_length(r, new_height / scale) * scale)

        radius_top = radius_values[0] + radius_values[1]
        radius_right = radius_values[5] + radius_values[6]
        radius_bottom = radius_values[2] + radius_values[3]
        radius_left = radius_values[4] + radius_values[7]
        alpha = min(
            1 if radius_top == 0 else new_width / radius_top,
            1 if radius_right == 0 else new_height / radius_right,
            1 if radius_bottom == 0 else new_width / radius_bottom,
            1 if radius_left == 0 else new_height / radius_left,
        )
        if alpha < 1:
            radius_values = tuple(alpha * i for i in radius_values)
        else:
            radius_values = tuple(radius_values)

        mask = get_rounded_rectangle_alpha((new_width, new_height), radius_values)
        if width is None:
            image.putalpha(mask)
        else:
            border.putalpha(mask)
            image.putalpha(
                get_rounded_rectangle_alpha(
                    image.size,
                    (
                        radius_values[0] - width_left,
                        radius_values[1] - width_right,
                        radius_values[2] - width_right,
                        radius_values[3] - width_left,
                        radius_values[4] - width_top,
                        radius_values[5] - width_top,
                        radius_values[6] - width_bottom,
                        radius_values[7] - width_bottom,
                    ),
                )
            )

    if width is None:
        if scale == 1:
            return image
        return get_resized_image(image, width=image.width / scale)
    else:
        border.paste(image, (width_left, width_top), image)
        if scale == 1:
            return border
        return get_resized_image(border, width=border.width / scale)


if __name__ == "__main__":
    # https://moyuanjun.github.io/coding/#/css/shape
    img = set_image_border(
        image=Image.new("RGB", (200, 200), "#91CAFF"),
        radius="50px",
        width="20px",
        color="#ff4d4f #597ef7 #ffc53d #73d13f",
    )

    scaled_2_img = set_image_border(
        image=Image.new("RGB", (200, 200), "#91CAFF"),
        radius="50px",
        width="20px",
        color="#ff4d4f #597ef7 #ffc53d #73d13f",
        scale=2,
    )

    scaled_10_img = set_image_border(
        image=Image.new("RGB", (200, 200), "#91CAFF"),
        radius="50px",
        width="20px",
        color="#ff4d4f #597ef7 #ffc53d #73d13f",
        scale=10,
    )

    im = get_merged_image([img, scaled_2_img, scaled_10_img], 640, space=20, number_per_row=3)
    bg = Image.new("RGB", (im.width + 40, im.height + 40), "grey")
    bg.paste(im, (20, 20), im)
    bg.save(__file__.replace(".py", ".png"))

from typing import List

from pydantic import BaseModel, Field

CYAN = "#d0d9de"
BLUE = "#4fb7ff"
GREY = "#939393"
BLACK = "#343233"
WHITE = "#fcfcfc"
ORANGE = "#eb7340"


class QRCode(BaseModel):
    enable: bool = True
    color_primary: str = BLACK
    color_secondary: str = "#f9f9f9"
    url: str = ""


class Footer(BaseModel):
    enable: bool = False
    color_background: str = "#f9f9f9"
    color_primary: str = "#666666"
    color_secondary: str = GREY
    text_primary: str = "扫描二维码查看动态"
    text_secondary: str = "{.url}"
    qrcode: QRCode = Field(default_factory=QRCode)


class ImagesMerge(BaseModel):
    enable: bool = True
    space: float = 0.01
    radius: str = "15%"
    number_per_row: int = 0
    max_number_per_row: int = 3


class Images(BaseModel):
    enable: bool = True
    max_height: float = 15
    merge: ImagesMerge = Field(default_factory=ImagesMerge)


class Reply(BaseModel):
    enable: bool = True
    radius: float = 0.03
    width: int = 2
    color: str = CYAN
    options: str = ""


class Content(BaseModel):
    enable: bool = True
    color_primary: str = BLACK
    color_secondary: str = "#4f7daf"
    size: str = "我不用脑子随手一写就是标标准准的二十个字"


class Description(BaseModel):
    enable: bool = True
    icon: bool = True
    size: float = 0.035
    color: str = GREY
    hoisting: bool = False


class Follow(BaseModel):
    enable: bool = True
    size: float = 0.035
    color_primary: str = BLACK
    color_secondary: str = GREY
    text: List[str] = ["{.follower} ", "粉丝    ", "{.following} ", "关注    ", "", "<edited?已编辑:>"]


class UID(BaseModel):
    enable: bool = False
    size: float = 0.035
    color: str = GREY
    prefix: str = "  @"


class Name(BaseModel):
    size: float = 0.05
    color: str = BLACK


class AvatarBorder(BaseModel):
    color: str = WHITE
    width: float = 0.05
    radius: str = "50%"


class Avatar(BaseModel):
    enable: bool = True
    width: float = 0.2
    offset: float = 0.23
    border: AvatarBorder = Field(default_factory=AvatarBorder)


class BannerImage(BaseModel):
    enable: bool = False
    index: int = -1
    ratio: float = 4
    offset: int = 0


class Banner(BaseModel):
    enable: bool = True
    color: str = BLUE
    radius: float = 0.03
    image: BannerImage = Field(default_factory=BannerImage)


class Options(BaseModel):
    width: int = 1000
    color: str = "white"
    banner: Banner = Field(default_factory=Banner)
    avatar: Avatar = Field(default_factory=Avatar)
    name: Name = Field(default_factory=Name)
    uid: UID = Field(default_factory=UID)
    follow: Follow = Field(default_factory=Follow)
    description: Description = Field(default_factory=Description)
    time: Description = Field(default_factory=Description)
    content: Content = Field(default_factory=Content)
    reply: Reply = Field(default_factory=Reply)
    images: Images = Field(default_factory=Images)
    footer: Footer = Field(default_factory=Footer)


if __name__ == "__main__":
    import os

    import tomli_w

    doc = Options().model_dump()
    with open(os.path.join(os.path.dirname(__file__), "default.toml"), "wb") as f:
        tomli_w.dump(doc, f)

import datetime
import json
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Attachment:
    url: str
    local: str = ""
    MIME: str = ""

    @property
    def data(self) -> dict:
        """
        返回字典格式对象
        """
        return {"url": self.url}

    def __str__(self) -> str:
        """
        返回字典格式经 json 处理后对象
        """
        return json.dumps(self.data, ensure_ascii=False)


@dataclass
class Job:
    id: int
    patten: str
    method: str
    url: str
    data: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)


@dataclass
class User:
    uid: str
    permission: float
    token: str = ""
    jobs: List[Job] = field(default_factory=list)
    listening: List[str] = field(default_factory=list)


@dataclass
class Blogger:
    platform: str
    uid: str
    name: str
    create: str
    follower: str
    following: str
    description: str
    face: Attachment
    pendant: Attachment

    @property
    def data(self) -> dict:
        """
        返回字典格式对象
        """
        dic = {}
        for k, v in self.__dict__.items():
            if k in ["face", "pendant"]:
                v: Attachment
                dic[k] = {} if v is None else v.data
            else:
                dic[k] = str(v)
        return dic
    
    def __str__(self) -> str:
        return json.dumps(self.data, ensure_ascii=False)


@dataclass
class Post:
    mid: str
    time: str
    text: str
    source: str
    blogger: Blogger    
    repost: "Post"
    comments: List["Post"]
    attachments: List[Attachment]
    submitter: User = None

    @property
    def date(self) -> str:
        """
        返回规定格式字符串时间
        """
        return datetime.datetime.fromtimestamp(float(self.time)).strftime("%H:%M:%S")

    @property
    def data(self) -> dict:
        """
        返回字典格式对象
        """
        dic = {}
        for k, v in self.__dict__.items():
            if k == "submitter":
                continue
            elif k == "blogger":
                dic[k] = self.blogger.data
            elif k == "attachments":
                dic[k] = [v.data for v in self.attachments]
            elif k == "repost":
                dic[k] = None if self.repost is None else self.repost.data
            elif k == "comments":
                dic[k] = [v.data for v in self.comments]
            else:
                if v is None:
                    continue
                dic[k] = str(v)
        return dic

    @property
    def json(self) -> dict:
        """
        返回字典格式经 json 处理后对象
        """
        dic = {}
        for k, v in self.__dict__.items():
            if k == "submitter":
                continue
            elif k == "attachments":
                dic[k] = [str(v) for v in self.attachments]
            elif k == "repost":
                dic[k] = "null" if self.repost is None else str(self.repost)
            elif k == "comments":
                dic[k] = [str(v) for v in self.comments]
            else:
                if v is None:
                    continue
                dic[k] = str(v)
        return dic

    def __str__(self) -> str:
        return json.dumps(self.data, ensure_ascii=False)


def parse(post: dict) -> Post:
    """
    递归解析
    """
    if post is None or len(post) == 0:
        return None
    post.update(post.pop("blogger"))
    return Post(
        face        = Attachment(**post.pop("face")),
        pendant     = Attachment(**post.pop("pendant")),
        attachments = [Attachment(**v) for v in post.pop("attachments")],
        repost      = parse(post.pop("repost")),
        comments    = [parse(v) for v in post.pop("comments")],
        submitter   = User(**post.pop("submitter")),
        **post
    )

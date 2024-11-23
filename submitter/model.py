import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Blog(BaseModel):
    """
    博文
    """

    id: int = None
    created_at: datetime = None

    submitter: str = None
    platform: str
    type: str
    uid: str
    mid: str

    url: str = None
    text: str
    time: datetime
    source: str = None
    edited: bool = None

    name: str
    avatar: str = None
    follower: str = None
    following: str = None
    description: str = None

    reply_id: Optional[int] = None
    reply: Optional["Blog"] = None
    comment_id: Optional[int] = None
    comments: Optional[List["Blog"]] = None

    assets: Optional[List[str]] = None
    banner: Optional[List[str]] = None
    extra: Optional[Dict[str, Any]] = None

    def __str__(self):
        return f'Blog({self.id}, {self.name}, "{self.text}"{", "+str(self.reply) if self.reply is not None else ""})'


class Role(Enum):
    """
    角色权限
    """

    Invalid = 0
    Normal = 1
    Trusted = 2
    Admin = 3
    Owner = 4


class RequestLog(BaseModel):
    """
    请求记录
    """

    blog_id: int
    created_at: datetime
    finished_at: datetime
    raw_result: str = None
    result: Optional[Any] = None
    error: str = None


class Filter(BaseModel):
    """
    博文筛选条件
    """

    submitter: str = None
    platform: str = None
    type: str = None
    uid: str = None


class Task(BaseModel):
    """
    任务
    """

    id: int = None
    created_at: datetime = None

    public: bool = None
    enable: bool = None
    name: str
    method: str
    url: str
    body: str = None
    header: Optional[Dict[str, str]] = None
    README: str = None
    fork_id: int = None
    fork_count: int = None

    filters: Optional[List[Filter]] = None
    logs: Optional[List[RequestLog]] = None
    user_id: str = None


class User(BaseModel):
    """
    用户
    """

    uid: str
    created_at: datetime
    ban: datetime
    role: Role
    name: str
    nickname: str
    tasks: Optional[List[Task]] = None


class Test(BaseModel):
    """
    测试任务
    """

    blog: Blog
    task: Task


class Tests(BaseModel):
    """
    测试任务集
    """

    blog: Blog
    tasks: List[int]


class BlogQuery(BaseModel):
    """
    查询条件
    """

    submitter: str = None
    platform: str = None
    type: str = None
    uid: str = None
    mid: str = None
    reply: bool = None
    comments: bool = None
    order: str = None
    limit: int = None
    offset: int = None
    conds: List[str] = None

    def items(self):
        return self.model_dump().items()


class BlogFilter(BaseModel):
    """
    筛选条件
    """

    filters: List[Filter]
    reply: bool = None
    comments: bool = None
    order: str = None
    limit: int = None
    offset: int = None
    conds: List[str] = None


class PatchBody(BaseModel):
    op: str
    path: str
    value: str = None

    def dumps(self, obj):
        self.value = json.dumps(obj, ensure_ascii=False)
        return self

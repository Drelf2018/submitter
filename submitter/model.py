import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Blog(BaseModel):
    """
    博文
    """

    id: Optional[int] = None  # 数据库内序号
    created_at: Optional[datetime] = None  # 数据库内创建时间

    submitter: Optional[str] = None  # 博文提交者
    platform: str  # 发布平台
    type: str  # 博文类型
    uid: str  # 账户序号
    mid: str  # 博文序号

    url: Optional[str] = None  # 博文网址
    text: str  # 文本内容
    time: datetime  # 发送时间
    title: Optional[str] = None  # 博文标题
    source: Optional[str] = None  # 博文来源
    edited: Optional[bool] = None  # 是否编辑

    name: Optional[str] = None  # 账户昵称
    avatar: Optional[str] = None  # 头像网址
    follower: Optional[str] = None  # 粉丝数量
    following: Optional[str] = None  # 关注数量
    description: Optional[str] = None  # 个人简介

    reply_id: Optional[int] = None  # 被本文回复的博文序号
    reply: Optional["Blog"] = None  # 被本文回复的博文
    comment_id: Optional[int] = None  # 被本文评论的博文序号
    comments: Optional[List["Blog"]] = None  # 本文的评论

    assets: Optional[List[str]] = None  # 资源网址
    banner: Optional[List[str]] = None  # 头图网址
    extra: Optional[Dict[str, Any]] = None  # 预留项

    def __str__(self):
        reply = ""
        if self.reply is not None:
            reply = ", " + str(self.reply)
        return f'Blog({self.name}, "{self.text}", {self.mid}{reply})'


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

    blog_id: int  # 该记录发送的博文序号
    created_at: datetime  # 开始请求时间
    finished_at: datetime  # 结束请求时间
    result: Any  # 响应为 JSON 会自动解析
    error: str  # 请求过程中发生的错误


class Filter(BaseModel):
    """
    筛选条件
    """

    submitter: str = ""  # 博文提交者
    platform: str = ""  # 发布平台
    type: str = ""  # 博文类型
    uid: str = ""  # 账户序号


class Task(BaseModel):
    """
    任务
    """

    id: Optional[int] = None  # 任务序号
    created_at: Optional[datetime] = None  # 任务创建时间

    public: Optional[bool] = None  # 是否公开
    enable: Optional[bool] = None  # 是否启用
    name: Optional[str] = None  # 任务名称
    icon: Optional[str] = None  # 任务图标
    method: Optional[str] = None  # 请求方法
    url: Optional[str] = None  # 请求地址
    body: Optional[str] = None  # 请求内容
    header: Optional[Dict[str, str]] = None  # 请求头部
    readme: Optional[str] = None  # 任务描述
    fork_id: Optional[int] = None  # 复刻来源
    fork_count: Optional[int] = None  # 被复刻次数

    filters: Optional[List[Filter]] = None  # 筛选条件
    logs: Optional[List[RequestLog]] = None  # 请求记录
    user_id: Optional[str] = None  # 所有者


class User(BaseModel):
    """
    用户
    """

    uid: str  # 用户序号
    created_at: datetime  # 建号时间
    ban: datetime  # 封禁结束时间
    role: Role  # 权限等级
    name: str  # 用户名
    nickname: str  # 昵称
    tasks: List[Task]  # 任务集


class Version(BaseModel):
    """
    版本信息
    """

    api: str  # 后端版本
    env: str  # 后端环境
    start: datetime  # 启动时间
    index: Optional[List[str]] = None  # 主页文件


class Condition(BaseModel):
    """
    查询条件
    """

    reply: bool = True  # 是否包含转发
    comments: bool = True  # 是否包含评论
    order: str = "time desc"  # 查询排列顺序
    limit: int = 30  # 查询行数
    offset: int = 0  # 查询偏移
    conds: Optional[List[str]] = None  # 其他条件


class PatchBody(BaseModel):
    """
    PATCH 请求体
    """

    op: str  # 操作类型，一般使用 `replace` 表示替换、`add` 表示添加、`remove` 表示移除
    path: str  # 操作路径，一般表示要操作的资源
    value: str = None  # 操作数据，一般表示替换、添加操作时的新值

    def dumps(self, obj):
        self.value = json.dumps(obj, ensure_ascii=False)
        return self


class Test(BaseModel):
    """
    任务测试请求体
    """

    blog: Optional[Blog] = None
    task: Optional[Task] = None
    blog_id: int = 0
    task_id: Optional[List[int]] = None

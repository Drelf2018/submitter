import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from ..data import Attachment, Attachments, Blogger, Post
from ..network import ApiException, Session


def created_at(text: str) -> int:
    """
    解析微博时间字段转为时间戳
    """
    return int(datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y").timestamp())


def created_at_comment(text: str) -> int:
    """
    标准化微博发布时间

    参考 https://github.com/Cloud-wish/Dynamic_Monitor/blob/main/main.py#L575
    """
    created_at = datetime.now()
    
    if u"分钟" in text:
        minute = text[:text.find(u"分钟")]
        minute = timedelta(minutes=int(minute))
        created_at -= minute
    elif u"小时" in text:
        hour = text[:text.find(u"小时")]
        hour = timedelta(hours=int(hour))
        created_at -= hour
    elif u"昨天" in text:
        created_at -= timedelta(days=1)
    elif text.count('-') != 0:
        if text.count('-') == 1:
            text = f"{created_at.year}-{text}"
        created_at = datetime.strptime(text, "%Y-%m-%d")
    return int(created_at.timestamp())


def deep_get(dic: dict, keys: str, default: Any = None) -> Any:
    """
    深度获取元素
    """
    kList = keys.split(".")
    for key in kList[:-1]:
        dic = dic.get(key, {})
    return dic.get(kList[-1], default)


@dataclass
class WeiboPost(Post):
    isTop: bool = False

    @staticmethod
    def parse(mblog: dict) -> "WeiboPost":
        """
        递归解析
        """
        if mblog is None or len(mblog) == 0:
            return None
        user: dict = mblog.get("user", {})
        return WeiboPost(
            mid     = mblog["mid"],
            time    = str(created_at(mblog["created_at"])),
            text    = mblog["text"],
            source  = mblog["source"],
            blogger = Blogger(
                platform    = "weibo",
                uid         = str(user.get("id")),
                name        = user.get("screen_name"),
                create      = str(int(time.time())),
                follower    = str(user.get("followers_count")),
                following   = str(user.get("follow_count")),
                description = user.get("description"),
                face        = Attachment(user.get("avatar_hd")),
                pendant     = None,
            ),
            repost      = WeiboPost.parse(mblog.get("retweeted_status")),
            comments    = [],
            attachments = [Attachment(p["large"]["url"]) for p in mblog.get("pics", [])],
            isTop       = deep_get(mblog, "title.text", "") == "置顶",
        )


def comment(com: dict) -> Post:
    """
    解析评论
    """
    if com is None or len(com) == 0:
        return None
    user: dict = com.get("user", {})
    return Post(
        mid     = str(com["id"]),
        time    = str(created_at_comment(com["created_at"])),
        text    = com["text"],
        source  = com["source"],
        blogger = Blogger(
            platform    = "weiboComment",
            uid         = str(user.get("id")),
            name        = user.get("screen_name"),
            create      = str(int(time.time())),
            follower    = str(user.get("followers_count")),
            following   = str(user.get("friends_count")),
            description = user.get("description", ""),
            face        = Attachment(user.get("profile_image_url")),
            pendant     = None,
        ),
        comments    = [],
        attachments = Attachments(deep_get(com, "pic.large.url")),
    )


class Weibo(Session):
    """
    微博适配器
    """
    def __init__(self, url: str = "https://m.weibo.cn/api", headers: dict | None = None) -> None:
        super().__init__(url, headers)

    def check_code(self, url: str, result: Any) -> ApiException | None:
        if result["ok"] != 1:
            return ApiException(url=url, code=result["ok"], **result)
        return None

    def data(self, result: Any) -> Any:
        return result["data"]

    async def posts(self, uid: str, page: int = 1):
        data, err = await self.get(f"/container/getIndex?containerid=107603{uid}&page={page}")
        if err is not None:
            logger.error(err)
            return
        for card in data["cards"]:
            if card["card_type"] != 9:
                continue
            yield WeiboPost.parse(card["mblog"])

    async def comments(self, post: Post):
        data, err = await self.get(f"/comments/show?id={post.mid}")
        if err is not None:
            logger.error(err)
            return
        for com in data["data"]:
            yield comment(com).set_repost(post)

        # 清空储存的评论
        # postName = post.type + post.mid
        # if self.usersComments.get(post.uid, None) is None:
        #     self.usersComments[post.uid] = Comments(postName)
        # elif self.usersComments[post.uid].post != postName:
        #     self.usersComments[post.uid] = Comments(postName)

        
            # mid = str(com["id"])
            # if mid in self.usersComments[post.uid].comments: continue

        #     com["attachment"] = [postName]
        #     com["repost"] = self.usersComments[post.uid].comments.get(str(com.get("reply_id", "")), None)
        #     self.usersComments[post.uid].comments[mid] = com
        #     yield WeiboComment.parse(com)
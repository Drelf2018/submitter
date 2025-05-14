from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import httpx

from ..client import ApiException
from ..model import Blog


def created_at(text: str) -> Optional[datetime]:
    """
    解析微博时间字段转为 datetime.datetime

    Args:
        text (str): 时间字符串

    Returns:
        `datetime` 时间
    """
    if text == "":
        return
    return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")


def created_at_comment(text: str) -> Optional[datetime]:
    """
    标准化微博发布时间

    参考 https://github.com/Cloud-wish/Dynamic_Monitor/blob/main/main.py#L575

    Args:
        text (str): 时间字符串

    Returns:
        `datetime` 时间
    """
    if text == "":
        return
    created_at = datetime.now()

    if "分钟" in text:
        minute = text[: text.find("分钟")]
        minute = timedelta(minutes=int(minute))
        created_at -= minute
    elif "小时" in text:
        hour = text[: text.find("小时")]
        hour = timedelta(hours=int(hour))
        created_at -= hour
    elif "昨天" in text:
        created_at -= timedelta(days=1)
    elif text.count("-") != 0:
        if text.count("-") == 1:
            text = f"{created_at.year}-{text}"
        created_at = datetime.strptime(text, "%Y-%m-%d")

    return created_at


def parse_mblog(mblog: dict) -> Optional[Blog]:
    """
    递归解析博文

    Args:
        mblog (dict): 微博信息字典

    Returns:
        格式化博文
    """
    if mblog is None:
        return None

    user: dict = mblog.get("user")
    if user is None:
        user = {}

    blog = Blog(
        platform="weibo",
        type="blog",
        uid=str(user.get("id", "")),
        mid=str(mblog["mid"]),
        #
        text=str(mblog.get("text", mblog.get("raw_text", ""))),
        time=created_at(mblog.get("created_at", "")),
        source=str(mblog.get("region_name", "")),
        edited=mblog.get("edit_config", {}).get("edited", False),
        #
        name=str(user.get("screen_name", "")),
        avatar=str(user.get("avatar_hd", "")),
        follower=str(user.get("followers_count", "")),
        following=str(user.get("follow_count", "")),
        description=str(user.get("description", "")),
        #
        extra={
            "is_top": mblog.get("title", {}).get("text") == "置顶",
            "source": mblog.get("source", ""),
        },
    )

    bid = mblog.get("bid")
    if bid is not None:
        blog.url = "https://m.weibo.cn/status/" + bid
    else:
        blog.url = "https://m.weibo.cn/status/" + blog.mid

    reply = parse_mblog(mblog.get("retweeted_status"))
    if reply is not None:
        blog.reply = reply

    pics: List[Dict[str, Dict[str, str]]] = mblog.get("pics")
    if pics is not None:
        blog.assets = []
        for p in pics:
            url = p.get("videoSrc")
            if url is not None:
                blog.assets.append(url)
            blog.assets.append(p.get("large", {}).get("url"))

    video = mblog.get("page_info", {}).get("urls", {}).get("mp4_720p_mp4")
    if video is not None:
        if blog.assets is None:
            blog.assets = [video]
        else:
            if video not in blog.assets:
                blog.assets.append(video)

    cover: str = user.get("cover_image_phone")
    if cover is not None:
        blog.banner = [cover]

    return blog


def parse_comment(comment: dict) -> Optional[Blog]:
    """
    解析评论

    Args:
        comment (dict): 微博评论信息字典

    Returns:
        格式化博文
    """
    if comment is None:
        return None

    user: dict = comment.get("user")
    if user is None:
        user = {}

    blog = Blog(
        platform="weibo",
        type="comment",
        uid=str(user.get("id", "")),
        mid=str(comment["id"]),
        #
        text=comment["text"],
        time=created_at_comment(comment["created_at"]),
        url=str(user.get("profile_url", "")),
        source=comment["source"],
        #
        name=str(user.get("screen_name", "")),
        avatar=str(user.get("profile_image_url", "")),
        follower=str(user.get("followers_count", "")),
        following=str(user.get("friends_count", "")),
    )

    pic: str = comment.get("pic", {}).get("large", {}).get("url")
    if pic is not None:
        blog.assets = [pic]

    return blog


class Weibo:
    """
    微博适配器
    """

    def __init__(self, base_url: str = "https://m.weibo.cn/api", headers: Optional[dict] = None, preload: Union[str, List[str], None] = None):
        self.session = httpx.AsyncClient(base_url=base_url, headers=headers)
        self.get_index_count = 0
        self.blogs: Dict[str, Blog] = {}
        self.comments: Dict[str, Blog] = {}
        if preload is None:
            self.preload = []
        elif isinstance(preload, str):
            self.preload = [preload]
        elif isinstance(preload, list):
            self.preload = preload

    async def __aenter__(self):
        for uid in self.preload:
            async for blog in self.get_index(uid):
                self.blogs[blog.mid] = blog
        return self

    async def __aexit__(self, exc_type, exc, tb): ...

    async def get_index(self, uid: str, page: int = 1):
        """
        获取已发布博文

        Args:
            uid (str): 用户ID
            page (int, optional): 起始页

        Raises:
            ApiException: 接口错误

        Yields:
            格式化博文
        """
        resp = await self.session.get(f"/container/getIndex?containerid=107603{uid}&page={page}", timeout=20)
        if resp.status_code != 200:
            raise ApiException(
                code=resp.status_code,
                error=f"<Response [{resp.status_code}]>",
            )
        result: dict = resp.json()
        if result["ok"] != 1:
            raise ApiException(code=result["ok"], error=result.get("msg", ""), data=result)
        self.get_index_count += 1
        for card in result["data"]["cards"]:
            if card["card_type"] == 9:
                yield parse_mblog(card["mblog"])

    async def get_new_index(self, uid: str, page: int = 1):
        """
        获取新发布博文

        Args:
            uid (str): 用户ID
            page (int, optional): 起始页

        Yields:
            格式化博文
        """
        async for blog in self.get_index(uid, page):
            if blog.mid not in self.blogs:
                self.blogs[blog.mid] = blog
                yield blog

    async def get_new_comments(self, blog: Blog):
        """
        获取新发布评论

        Args:
            blog (Blog): 微博博文

        Raises:
            ApiException: 接口错误

        Yields:
            该微博下评论
        """
        resp = await self.session.get("/comments/show?id=" + blog.mid)
        result: dict = resp.json()
        if result["ok"] == 0:
            return
        elif result["ok"] != 1:
            raise ApiException(code=result["ok"], error=result.get("msg", ""), data=result)

        for comment in result["data"]["data"][::-1]:
            cmt = parse_comment(comment)
            if cmt.mid in self.comments:
                continue
            cmt.comment_id = blog.id

            reply = self.comments.get(str(comment.get("reply_id", "")))
            if reply is not None:
                if reply.id is not None:
                    cmt.reply_id = reply.id
                else:
                    cmt.reply = reply

            self.comments[cmt.mid] = cmt
            yield cmt

    def delete_blog(self, blog: Blog):
        """
        删除已记录微博及其评论

        Args:
            blog (Blog): 要删除的微博
        """
        for cmt in self.comments.values():
            if cmt.comment_id == blog.id:
                self.comments.pop(cmt.mid)
        self.blogs.pop(blog.mid)

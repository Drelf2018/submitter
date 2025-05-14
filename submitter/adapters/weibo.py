from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from ..client import ApiException, Session
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


class Result(BaseModel):
    ok: Optional[int] = None
    data: Optional[Any] = None
    msg: Optional[str] = None


class Weibo(Session):
    """
    微博适配器
    """

    def __init__(
        self,
        base_url: str = "https://m.weibo.cn/api",
        headers: Optional[dict] = None,
        cookies: Optional[dict] = None,
        preload: Union[str, List[str], None] = None,
    ):
        """
        Args:
            base_url (str): 基础接口地址
            headers (dict): 请求头
            cookies (dict): Cookies
            preload (Union[str, List[str], None]): 预加载给定博主的微博
        """
        Session.__init__(self, base_url, headers=headers, cookies=cookies)
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
            try:
                async for blog in self.get_index(uid):
                    self.blogs[blog.mid] = blog
            except:
                pass
        return self

    async def __aexit__(self, exc_type, exc, tb): ...

    async def request(self, method: str, url: str, *args, **kwargs):
        """
        检查业务码的请求

        Args:
            method (str): 请求方法
            url (str): 请求地址
        """
        r = Result.model_validate_json(await super().request(method, url, *args, **kwargs))
        if r.ok != 1:
            raise ApiException(r.ok, r.msg)
        return r.data

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
        r: Dict[str, List[dict]] = await self.get(f"/container/getIndex?containerid=107603{uid}&page={page}", timeout=20)
        for card in r.get("cards", []):
            if card.get("card_type") == 9:
                blog = parse_mblog(card.get("mblog"))
                if blog is not None:
                    yield blog

    async def get_new_index(self, uid: str, page: int = 1):
        """
        获取新发布博文

        Args:
            uid (str): 用户ID
            page (int, optional): 起始页

        Raises:
            ApiException: 接口错误

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
        r: Dict[str, List[dict]] = await self.get(f"/comments/show?id={blog.mid}")
        for data in r.get("data", [])[::-1]:  # 从旧到新
            comment = parse_comment(data)
            if comment.mid in self.comments:
                continue
            comment.comment_id = blog.id

            reply = self.comments.get(str(data.get("reply_id", "")))
            if reply is not None:
                if reply.id is not None:
                    comment.reply_id = reply.id
                else:
                    comment.reply = reply

            self.comments[comment.mid] = comment
            yield comment

    async def create_comment(self, mid: str, comment: str, is_repost: int = 0) -> dict:
        """
        发布评论

        Args:
            mid (str): 微博平台内博文的序号
            comment (str): 评论内容
            is_repost (int): 是否同时转发

        Returns:
            一个字段非常多的字典，非常不建议细究返回值，捕获错误就好了
        """
        return await self.post("https://weibo.com/ajax/comments/create", data={"id": mid, "comment": comment, "is_repost": is_repost})

    def delete_blog(self, blog: Blog):
        """
        删除本地记录的微博及其评论

        Args:
            blog (Blog): 要删除的微博
        """
        for cmt in self.comments.values():
            if cmt.comment_id == blog.id:
                self.comments.pop(cmt.mid)
        self.blogs.pop(blog.mid)

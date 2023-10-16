from loguru import logger

from submitter import Submitter, Weibo

URL = "http://localhost:9000"
TOKEN = "********"
UID = "188888131"
SESSDATA = "24f29131,1712767560,2c336*a1CjAQlzix9vartofMcQ9-L7ntc0iQbmN35-0rh2aXPCCnJo4za5OiV73Kk01hkn6yzUcSVlR2QkdDM1lOeGEyNy0wMnpiNUdzUWJRLXBOQXBQcUpnT0pveVdZNmpRYU5KZkZNaHFCQ0tmVjE5YWNZVTJiWEhYTFRoY0MtRDc0WENiSlNjek9XRUFnIIEC"
BILI_JCT = "bf6c87924f97df389cf4932683fc5a9a"
PostList = []


@Submitter(url=URL, token=TOKEN, dedeuserid=UID, sessdata=SESSDATA, bili_jct=BILI_JCT)
async def _(sub: Submitter):
    logger.info(f"version: {await sub.version()}")
    wb = Weibo()
    @sub.job(interval=5, uid=7198559139)
    async def _(uid: int):
        if len(PostList) == 0:
            async for post in wb.posts(uid):
                PostList.append(post.mid)
            return
        lastest = None
        async for post in wb.posts(uid):
            if lastest is None and not post.isTop:
                lastest = post
            if post.mid not in PostList:
                PostList.append(post.mid)
                logger.info(post)
                err = await sub.submit(post)
                if err is not None:
                    logger.error(err)
                else:
                    logger.info("提交成功")
        # if lastest is not None:
        #     async for comment in wb.comments(lastest):
        #         print(comment)
        #         if comment.blogger.uid == uid:
        #             await sub.submit(comment)

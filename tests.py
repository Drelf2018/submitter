from submitter import *

URL = "http://localhost:9000"
TOKEN = "********"

data = {
    "mid":         "2",
    "time":        "1690442897",
    "text":        "你好李鑫",
    "source":      "来自牛魔",
    "platform":    "bilibili",
    "uid":         "434334701",
    "name":        "七海Nana7mi",
    "create":      "1690442797",
    "follower":    "989643",
    "following":   "551",
    "description": "大家好，测试这里",

    "face":        Attachment("https://i2.hdslb.com/bfs/face/f261f5395f1f0082b106f7a23b9424a922b046bb.jpg"),
    "pendant":     Attachment("https://i1.hdslb.com/bfs/face/86faab4844dd2c45870fdafa8f2c9ce7be3e999f.jpg"),    
    "attachments": [
        Attachment("https://i1.hdslb.com/bfs/face/86faab4844dd2c45870fdafa8f2c9ce7be3e999f.jpg"),
        Attachment("https://i2.hdslb.com/bfs/face/f261f5395f1f0082b106f7a23b9424a922b046bb.jpg"),
    ],

    "repost":   None,
    "comments": [],
}
p = Post(**data)

@Submitter(url=URL, token=TOKEN)
async def _(sub: Submitter):
    @sub.job(once=True)
    async def _():
        err = await sub.submit(p)
        if isinstance(err, ApiException):
            print("ApiException:", err)
        elif isinstance(err, Exception):
            print("Exception:", err)

    @sub.job(3, 3)
    async def _():
        posts = await sub.posts(begin="1690442894")
        for p in posts:
            print(">>>", p)

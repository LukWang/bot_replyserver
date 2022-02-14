from botoy import GroupMsg, MsgTypes
import json
import re


def common_group_middleware(ctx: GroupMsg):
    if GroupMsg.MsgType == MsgTypes.PicMsg or GroupMsg.MsgType == MsgTypes.AtMsg:
        content_json = json.loads(ctx.Content)
        ctx.Content = content_json["Content"]
        if "UserExt" in content_json:
            ctx.target = []
            for user in content_json["UserExt"]:
                ctx.Content = re.sub(f"@{user['QQNick']}\\s+", "", ctx.Content)
                ctx.target.append(user['QQUid'])


'''
            {
                "Content": "@FuFu fufu",
                "GroupPic": [
                    {
                        "FileId": 2168045463,
                        "FileMd5": "J59bsRMlpifqfR3uElO0lA==",
                        "FileSize": 6211,
                        "ForwordBuf": "EiQyNzlGNUJCMTEzMjVBNjI3RUE3RDFERUUxMjUzQjQ5NC5naWY4l//miQhA7Z6OrwZIUFBCWhB2V2lYYU5kVDV1TWFaQUo5YAFqECefW7ETJaYn6n0d7hJTtJRyWy9nY2hhdHBpY19uZXcvMTEzNTE4ODk0MS81OTk4MzEwNTgtMjE2ODA0NTQ2My0yNzlGNUJCMTEzMjVBNjI3RUE3RDFERUUxMjUzQjQ5NC8xOTg/dGVybT0yNTWCAVkvZ2NoYXRwaWNfbmV3LzExMzUxODg5NDEvNTk5ODMxMDU4LTIxNjgwNDU0NjMtMjc5RjVCQjExMzI1QTYyN0VBN0QxREVFMTI1M0I0OTQvMD90ZXJtPTI1NYgBAKAB0A+wATy4ATzAAcgByAHDMNABAOgBAPABAPoBWy9nY2hhdHBpY19uZXcvMTEzNTE4ODk0MS81OTk4MzEwNTgtMjE2ODA0NTQ2My0yNzlGNUJCMTEzMjVBNjI3RUE3RDFERUUxMjUzQjQ5NC80MDA/dGVybT0yNTWSAhoIABAAMgBKDlvliqjnlLvooajmg4VdUAB4Bg==",
                        "ForwordField": 8,
                        "Url": "http://gchat.qpic.cn/gchatpic_new/1135188941/599831058-2534335053-279F5BB11325A627EA7D1DEE1253B494/0?vuin=2782720791\\u0026term=255\\u0026pictype=0"
                    }
                ],
                "Tips": "[群图片]",
                "UserExt": [
                    {
                        "QQNick": "FuFu",
                        "QQUid": 2782720791
                    }
                ],
                "UserID": [
                    2782720791
                ]
            }
'''
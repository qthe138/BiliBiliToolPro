import json
import os
import time
from decimal import Decimal, InvalidOperation
from urllib import error, parse, request


API = "https://api.bilibili.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


class BiliError(Exception):
    pass


def main_handler(event=None, context=None):
    try:
        return {"ok": True, "result": run()}
    except Exception as exc:
        print("[fatal] {}".format(exc))
        return {"ok": False, "error": str(exc)}


def run():
    config = load_config()
    cookie = config["cookie"]
    user = get_user(cookie)
    result = {
        "mid": pick(user, "mid", "Mid"),
        "vip_type": pick(user, "vipType", "VipType"),
        "coupon_before": str(coupon_balance(user)),
        "received": [],
        "charge": None,
    }

    if not annual_vip(user):
        print("[skip] annual VIP is required")
        return result

    tasks = set(x.strip().lower() for x in config["run_tasks"].replace(",", "&").split("&") if x.strip())
    if "all" in tasks or "vipprivilege" in tasks:
        for privilege_type, name in ((1, "B-coin coupon"), (2, "member benefits")):
            response = bili_request(
                "POST",
                API + "/x/vip/privilege/receive?" + parse.urlencode({"type": privilege_type, "csrf": config["csrf"]}),
                cookie,
                form={},
            )
            ok = response.get("code") == 0
            print("[receive] {}: {}".format(name, "ok" if ok else response.get("message")))
            result["received"].append({"type": privilege_type, "ok": ok, "message": response.get("message")})
            time.sleep(1)
        user = get_user(cookie)

    if "all" in tasks or "charge" in tasks:
        result["charge"] = charge(config, user)
    return result


def load_config():
    cookie = os.environ.get("BILI_COOKIE", "").strip()
    if not cookie:
        raise ValueError("missing BILI_COOKIE repository secret")
    items = parse_cookie(cookie)
    csrf = items.get("bili_jct", "")
    if not items.get("SESSDATA") or not csrf:
        raise ValueError("BILI_COOKIE must contain SESSDATA and bili_jct")
    return {
        "cookie": cookie,
        "csrf": csrf,
        "target_up_id": os.environ.get("TARGET_UP_ID", "98399918").strip(),
        "comment": os.environ.get("CHARGE_COMMENT", "支持"),
        "min_coupon": decimal_value(os.environ.get("MIN_COUPON_BALANCE", "2")),
        "charge_amount": decimal_value(os.environ.get("CHARGE_AMOUNT", "")),
        "run_tasks": os.environ.get("RUN_TASKS", "VipPrivilege&Charge"),
    }


def parse_cookie(cookie):
    result = {}
    for item in cookie.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def get_user(cookie):
    response = bili_request("GET", API + "/x/web-interface/nav", cookie)
    if response.get("code") != 0:
        raise BiliError("login check failed: {}".format(response.get("message")))
    data = response.get("data") or {}
    if not pick(data, "isLogin", "IsLogin", default=False):
        raise BiliError("BILI_COOKIE is expired or invalid")
    print(
        "[user] {} vip_type={} coupon={}".format(
            pick(data, "uname", "Uname", default=""),
            pick(data, "vipType", "VipType", default=0),
            coupon_balance(data),
        )
    )
    return data


def annual_vip(user):
    try:
        return int(pick(user, "vipStatus", "VipStatus", default=0)) == 1 and int(
            pick(user, "vipType", "VipType", default=0)
        ) == 2
    except (TypeError, ValueError):
        return False


def coupon_balance(user):
    wallet = pick(user, "wallet", "Wallet", default={}) or {}
    value = pick(wallet, "coupon_balance", "Coupon_balance", "couponBalance", default=0)
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def charge(config, user):
    balance = coupon_balance(user)
    amount = config["charge_amount"] or balance
    amount = min(amount, balance)
    if amount < config["min_coupon"]:
        message = "coupon balance {} is below minimum {}".format(balance, config["min_coupon"])
        print("[skip] {}".format(message))
        return {"skipped": True, "message": message}
    if not config["target_up_id"].isdigit():
        raise ValueError("TARGET_UP_ID must be a numeric UID")

    form = {
        "bp_num": decimal_text(amount),
        "is_bp_remains_prior": "true",
        "up_mid": config["target_up_id"],
        "otype": "up",
        "oid": config["target_up_id"],
        "csrf": config["csrf"],
    }
    response = bili_request(
        "POST",
        API + "/x/ugcpay/web/v2/trade/elec/pay/quick",
        config["cookie"],
        form=form,
        referer=True,
    )
    data = response.get("data") or {}
    status = pick(data, "status", "Status", default=None)
    ok = response.get("code") == 0 and str(status) == "4"
    print("[charge] {}".format("ok" if ok else response.get("message") or data.get("msg")))
    order_no = pick(data, "order_no", "Order_no", default="")
    comment = None
    if ok and order_no and config["comment"]:
        comment_response = bili_request(
            "POST",
            API + "/x/ugcpay/trade/elec/message",
            config["cookie"],
            form={"order_id": order_no, "message": config["comment"], "csrf": config["csrf"]},
            referer=True,
        )
        comment = comment_response.get("code") == 0
        print("[comment] {}".format("ok" if comment else comment_response.get("message")))
    return {"ok": ok, "amount": decimal_text(amount), "target_up_id": config["target_up_id"], "order_no": order_no, "comment": comment}


def bili_request(method, url, cookie, form=None, referer=False):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
        "User-Agent": USER_AGENT,
    }
    if referer:
        headers["Referer"] = "https://www.bilibili.com/"
        headers["Origin"] = "https://www.bilibili.com"
    body = None
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = parse.urlencode(form or {}).encode("utf-8")
    last_error = None
    for attempt in range(3):
        try:
            req = request.Request(url, data=body, headers=headers, method=method)
            with request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            last_error = "HTTP {}".format(exc.code)
        except Exception as exc:
            last_error = str(exc)
        if attempt < 2:
            time.sleep(attempt + 1)
    raise BiliError(last_error or "request failed")


def pick(data, *keys, **kwargs):
    default = kwargs.get("default")
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data[key]
    return default


def decimal_value(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError("invalid decimal value: {}".format(value))


def decimal_text(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


if __name__ == "__main__":
    print(json.dumps(main_handler(), ensure_ascii=False, indent=2))

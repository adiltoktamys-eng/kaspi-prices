"""Текущие цены Каспи по списку товаров (ids.json) -> prices.json.

Запускается в GitHub Actions по расписанию и по кнопке «Run workflow»: компьютер и Claude не нужны.
Цена = минимальная среди продавцов (POST /yml/offer-view/offers/{id}, сортировка по цене).
prices.json: {"at": "2026-11-25T03:00:00Z", "p": {"<id>": [цена или null, продавцов], ...}}
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

CITY, ZONE = "750000000", "Magnum_ZONE1"   # Алматы — как в разведке
THREADS, PAUSE = 3, 0.7
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9", "Accept": "application/json"})


def fetch(pid):
    body = {"cityId": CITY, "id": str(pid), "merchantUID": [], "limit": 1, "page": 0, "sortOption": "PRICE",
            "highRating": None, "searchText": None, "zoneId": [ZONE], "installationId": "-1"}
    for attempt in range(3):
        try:
            r = s.post(f"https://kaspi.kz/yml/offer-view/offers/{pid}", json=body, timeout=30,
                       headers={"Referer": f"https://kaspi.kz/shop/p/-{pid}/"})
            if r.status_code in (429, 503):
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            d = r.json()
            prices = [o.get("price") for o in d.get("offers") or [] if o.get("price")]
            count = d.get("offersCount") or d.get("total") or len(prices)
            return [int(min(prices)) if prices else None, int(count)]
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None


def main():
    ids = json.load(open("ids.json"))
    try:
        old = json.load(open("prices.json")).get("p", {})
    except Exception:
        old = {}
    t0 = time.time()
    out, failed = {}, 0

    def job(pid):
        r = fetch(pid)
        time.sleep(PAUSE)
        return pid, r

    with ThreadPoolExecutor(THREADS) as ex:
        for pid, r in ex.map(job, ids):
            if r is None:
                failed += 1
                if pid in old:
                    out[pid] = old[pid]  # Каспи не ответил — оставляем прошлую цену
            else:
                out[pid] = r
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump({"at": at, "p": out}, open("prices.json", "w"), separators=(",", ":"))
    changed = sum(1 for k, v in out.items() if old.get(k) and old[k][0] != v[0])
    print(f"{len(out)} товаров, изменилось {changed}, не ответило {failed}, {time.time() - t0:.0f} с")
    if failed > len(ids) // 2:
        sys.exit(1)  # что-то сломалось — не считаем запуск успешным


if __name__ == "__main__":
    main()

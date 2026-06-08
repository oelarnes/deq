import argparse
import re
import sys
from urllib.parse import urlencode

from deq.sample_pack import DEQ_URL, fetch_draft_pick

_17L_DRAFT_BASE = "https://www.17lands.com/draft"
_SET_CODE_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]{1,5}$')


def _normalize_to_url(ref: str, pack: int, pick: int) -> str:
    if ref.startswith("http"):
        return ref
    parts = ref.strip("/").split("/")
    if len(parts) == 3:
        draft_id, p, pk = parts
        return f"{_17L_DRAFT_BASE}/{draft_id}/{p}/{pk}"
    if len(parts) == 1:
        return f"{_17L_DRAFT_BASE}/{ref}/{pack}/{pick}"
    print(f"error: cannot parse draft reference {ref!r}", file=sys.stderr)
    sys.exit(1)


def _parse_ref(ref: str, pack: int, pick: int) -> dict:
    """Parse the main argument into a typed draft reference.

    Returns {'kind': 'set', 'set_code': str}
         or {'kind': 'pick', 'url': str}.
    """
    if _SET_CODE_RE.match(ref):
        return {"kind": "set", "set_code": ref}
    return {"kind": "pick", "url": _normalize_to_url(ref, pack, pick)}


def _cmd_link(args: argparse.Namespace) -> None:
    ref = _parse_ref(args.draft_ref, args.pack, args.pick)
    sort = args.sort or ("deq" if args.asc else None)

    if ref["kind"] == "set":
        q_parts = []
        if args.color:
            q_parts.append(f"c:{args.color}")
        if args.rarity:
            q_parts.append(f"r:{args.rarity}")
        params = {"set": ref["set_code"]}
        if q_parts:
            params["q"] = " ".join(q_parts)
        if args.card:
            params["card"] = args.card
        if sort:
            params["sort"] = f"{sort}:{'asc' if args.asc else 'desc'}"
        if args.k:
            params["k"] = args.k
        print(args.base_url + "?" + urlencode(params))
    else:
        draft_pick = fetch_draft_pick(ref["url"])
        print(draft_pick.deq_query_str(
            card_name=args.card,
            color=args.color,
            rarity=args.rarity,
            sort=sort,
            asc=args.asc,
            k=args.k,
            base_url=args.base_url,
        ))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="deq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    link = subparsers.add_parser("link", help="Output a DEq site URL for a set or draft pick.")
    link.add_argument("draft_ref", metavar="DRAFT_REF", help="set code, 17lands link, draft_id, or draft_id/pack/pick")
    link.add_argument("--pack", type=int, default=1, metavar="N", help="pack number when using bare draft_id (default 1)")
    link.add_argument("--pick", type=int, default=1, metavar="N", help="pick number when using bare draft_id (default 1)")
    link.add_argument("-c", "--color", metavar="FILTER", help="color filter, e.g. wb* or u/r")
    link.add_argument("-r", "--rarity", metavar="FILTER", help="rarity filter, e.g. common or uncommon/rare")
    link.add_argument("--card", metavar="NAME", help="also open this card's modal in the DEq URL")
    link.add_argument("--sort", metavar="COL", help="sort column, e.g. adj, deq, mwr, name")
    link.add_argument("--asc", action="store_true", help="sort ascending (default is descending)")
    link.add_argument("-k", type=int, metavar="N", dest="k", help="open the modal for the Nth ranked card")
    link.add_argument("--base-url", metavar="URL", default=DEQ_URL, dest="base_url", help="DEq base URL")

    args = parser.parse_args(argv)

    if args.command == "link":
        _cmd_link(args)

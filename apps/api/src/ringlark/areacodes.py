"""A coarse check of a US or Canadian number's area code against the time zone given for the person.

The calling window is worked out from the time zone in the list, and nothing else tells the dialer where a person is. A list exported with one default zone would put
every 9:00 start at 6:00 in the morning for a person in Los Angeles. This module compares the area code with the zone and gives a WARNING, never a block: people keep their
number when they move, and the table is partial on purpose. It only holds area codes that lie inside one standard time zone; a code that is not in it is not checked.
Zones are compared by their winter offset from UTC, so Arizona (no daylight saving) agrees with Mountain.
"""

from __future__ import annotations

from datetime import datetime

from ringlark.util import zone

# Standard (winter) offset from UTC in hours, then the area codes. Partial: codes that cross a zone line (for example the Florida panhandle, western Kansas, the Dakotas,
# north Idaho, the Upper Peninsula of Michigan) are left out.
_EASTERN = """201 202 203 207 212 215 216 220 223 229 234 239 240 248 252 260 267 272 276 283 301 302 304 305 313 315 317 321 326 330 332 336 339 347 351 352 380 386 401 404 407 410 412 413 419 423 434 440
 443 445 463 470 475 478 484 502 508 513 516 517 518 540 551 561 567 570 571 582 585 586 603 606 607 609 610 614 616 617 631 640 646 656 667 678 680 681 686 689 703 704 716 717 718 724 727 732 734
 740 743 754 757 762 765 770 772 774 781 786 802 803 804 810 813 828 835 838 839 843 845 848 854 856 857 859 860 862 863 864 865 878 904 908 910 912 914 917 919 929 934 937 941 943 947 948 954 959
 973 978 980 984 989"""
_CENTRAL = """205 210 214 217 218 224 225 228 251 254 256 262 274 281 309 312 314 316 318 319 320 325 331 334 337 346 361 402 405 409 414 417 430 432 464 469 479 501 504 507 512 515 531 534 539 557 563 572 573
 580 601 608 612 615 618 629 630 636 641 651 659 660 662 682 708 712 713 715 731 737 763 769 773 779 806 815 816 817 830 832 847 870 872 901 903 913 918 920 936 938 940 952 956 972 979 985"""
_MOUNTAIN = "303 307 385 406 435 480 505 520 575 602 623 719 720 801 915 928 970 983"
_PACIFIC = """206 209 213 253 279 310 323 341 360 408 415 424 425 442 503 509 510 530 559 562 564 619 626 628 650 657 661 669 702 707 714 725 747 760 775 805 818 820 831 840 858 916 925 949 951 971"""
_ALASKA = "907"
_HAWAII = "808"

OFFSETS = {-5: _EASTERN, -6: _CENTRAL, -7: _MOUNTAIN, -8: _PACIFIC, -9: _ALASKA, -10: _HAWAII}
EXPECTED: dict[str, int] = {code: offset for offset, codes in OFFSETS.items() for code in codes.split()}
_JAN = datetime(2026, 1, 15, 12, 0)


def winter_offset(tz_name: str) -> int | None:
    z = zone(tz_name)
    if z is None:
        return None
    off = _JAN.replace(tzinfo=z).utcoffset()
    return None if off is None else int(off.total_seconds() // 3600)


def area_code(phone: str) -> str:
    """The three digit area code of a +1 number, or "" for any other number."""
    return phone[2:5] if phone.startswith("+1") and len(phone) == 12 else ""


def mismatch(phone: str, tz_name: str) -> tuple[str, int, int] | None:
    """(area code, the zone offset the code usually has, the offset of the zone given) when they differ; None when they agree, when the code is not in the table, or when
    the zone is unknown (that is its own flag)."""
    code = area_code(phone)
    expected, given = EXPECTED.get(code), winter_offset(tz_name)
    if expected is None or given is None or expected == given:
        return None
    return code, expected, given

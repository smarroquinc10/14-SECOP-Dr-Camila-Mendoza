"""Save the HTML of an OpportunityDetail page so we can write a proper bs4 parser."""
import os
from pathlib import Path

# Use the existing scraper which already handles captcha + persistent profile
from secop_ii.portal_scraper import PortalScraper

OUT = Path("_opp_5405127.html")

with PortalScraper() as s:
    # Force a fresh fetch by clearing cache for this NTC
    if "CO1.NTC.5405127" in s._cache:
        del s._cache["CO1.NTC.5405127"]
    page = s._browser.new_page()
    try:
        page.goto(
            "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5405127&isFromPublicArea=True&isModal=False",
            timeout=30000,
        )
        page.wait_for_load_state("networkidle", timeout=20000)
        html = page.content()
        OUT.write_text(html, encoding="utf-8")
        print(f"saved {len(html)} bytes to {OUT}")
    finally:
        page.close()

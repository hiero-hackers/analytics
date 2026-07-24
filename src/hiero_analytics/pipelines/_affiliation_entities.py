"""Curated entity maps for the affiliation resolver.

Pure data, edited by hand as the ecosystem changes: employer email domains,
company-field spellings, org-membership handles, and the deliberately small
curated list of solo/consultancy domains (an uncurated personal domain is
never minted into an org — those people stay Independent). Lineage rules
live here too: Swirlds Labs was renamed to Hashgraph; Hedera and Hgraph
stay separate entities.
"""

from __future__ import annotations

NOREPLY = "users.noreply.github.com"

# --- entity maps (each a distinct entity; Swirlds Labs folded into Hashgraph) ---
EMAIL_DOMAIN = {
    "swirldslabs.com": "Hashgraph",
    "swirlds.com": "Hashgraph",
    "hashgraph.com": "Hashgraph",
    "hedera.com": "Hedera",
    "hgraph.com": "Hgraph",
    "limechain.tech": "LimeChain",
    "limehcain.tech": "LimeChain",
    "openelements.com": "OpenElements",
    "open-elements.com": "OpenElements",
    "dsr-corporation.com": "DSR Corporation",
    "linuxfoundation.org": "Linux Foundation",
    "blockydevs.com": "BlockyDevs",
    "launchbadge.com": "Launchbadge",
}
COMPANY_FULL = {
    # 'Hedera Hashgraph LLC' is the old unified company name (ancestor of both the
    # Hashgraph engineering company and the Hedera network entity); on its own it
    # means the Hedera side. Actual Hashgraph staff resolve via their work email.
    "hedera hashgraph llc": "Hedera",
    "hedera hashgraph": "Hedera",
    "swirlds labs": "Hashgraph",
    "the hashgraph association (tha)": "The Hashgraph Association",
    "the hashgraph association": "The Hashgraph Association",
    "hashgraph-association": "The Hashgraph Association",
    "the linux foundation": "Linux Foundation",
    "linux foundation": "Linux Foundation",
    "dsr corporation": "DSR Corporation",
    "open elements gmbh": "OpenElements",
    "turtle moon llc": "Turtle Moon",
    "jitty labs": "Jitty Labs",
    "guy who builds for fun": None,
}
COMPANY_TOKEN = {
    "hashgraph": "Hashgraph",
    "swirlds": "Hashgraph",
    "swirldslabs": "Hashgraph",
    "hgraph": "Hgraph",
    "hedera": "Hedera",
    "openelements": "OpenElements",
    "limechain": "LimeChain",
    "linuxfoundation": "Linux Foundation",
    "launchbadge": "Launchbadge",
    "blockydevs": "BlockyDevs",
    "dsr": "DSR Corporation",
}
EMPLOYER_ORG = {
    "hashgraph": "Hashgraph",
    "swirldslabs": "Hashgraph",
    "swirlds": "Hashgraph",
    "openelements": "OpenElements",
    "hashgraph-association": "The Hashgraph Association",
    "limechain": "LimeChain",
}
SMALL_ORG_NAME = {
    "devlabs.bg": "DevLabs",
    "goodmorning.dev": "DevLabs",
    "onepiece.software": "Onepiece Software",
    "gradle.com": "Gradle",
    "8bees.fr": "8bees",
    "capsule03.com": "Capsule03",
    "sydor.dev": "Sydor",
    "labeltech.io": "LabelTech",
    "jcovalent.com": "JCovalent",
    "servercurio.com": "ServerCurio",
    "zkbricks.com": "zkBricks",
    "retrove.io": "Retrove",
    "pandaswhocode.com": "Pandas Who Code",
}
SMALL_ORG_FROM_COMPANY = {"hol": "Hashgraph Online"}
SMALL_ORG_FROM_ORG = {"hashgraph-online": "Hashgraph Online"}
MD_COMPANY = {
    "hashpack": "HashPack",
    "onepiece": "Onepiece Software",
    "8bees": "8bees",
    "capsule03": "Capsule03",
    "turtlemoon": "Turtle Moon",
    "hol": "Hashgraph Online",
}
MD_COMPANY_FULL = {
    "hashgraph online": "Hashgraph Online",
    "open elements": "OpenElements",
    "hedera foundation": "Hedera",
    "turtle moon": "Turtle Moon",
    "milanwr.com (8bees)": "8bees",
}
PERSONAL_DOMAINS = {
    "gmail.com",
    NOREPLY,
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "web.de",
    "yahoo.com",
    "qq.com",
    "abv.bg",
    "pacbell.net",
    "news.co.uk",
}
MD_SKIP = {"", "-", "n/a", "none", "tbd"}

# Company-field values that aren't an employer (so they don't become a named org).
COMPANY_JUNK = {
    "",
    "-",
    "n/a",
    "none",
    "self",
    "self employed",
    "self-employed",
    "freelance",
    "freelancer",
    "freelancing",
    "independent",
    "me",
    "myself",
    "open source",
    "opensource",
    "various",
    "remote",
    "home",
    "world",
    "earth",
    "internet",
    "the internet",
    "student",
    "unemployed",
    "looking",
    "open to work",
    "none of your business",
    "stealth mode startup",
    "stealth",
    "stealth startup",
    "blog",
    "live",
    "crypto",
    "web3",
    "blockchain",
}
COMPANY_NOT_EMPLOYER = {"hiero-ledger", "hiero-hackers", "hiero", "lf-decentralized-trust"}

import os
import sys
import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv
import argparse

# Config.
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")

# Icons
ICON_GITHUB = "🔗"
ICON_X = "❌"
ICON_CHECK = "✅"
ICON_BULB = "💡"
ICON_WARNING = "⚠️"
ICON_CRAWL = "🔍"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}"
} if GITHUB_TOKEN else {}

# Config check.
def check_config():
    missing = []
    if not NEO4J_URI:
        missing.append("NEO4J_URI")
    if not NEO4J_USER:
        missing.append("NEO4J_USER")
    if not NEO4J_PASS:
        missing.append("NEO4J_PASS")
    if missing:
        print(f"{ICON_X} Missing config variables: {', '.join(missing)}")
        print(f"{ICON_BULB} Make sure you have a .env file or environment variables set.")
        sys.exit(1)
    if not GITHUB_TOKEN:
        print(f"{ICON_WARNING} No GITHUB_TOKEN provided. You may hit rate limits.")
        print(f"{ICON_BULB} Consider setting a token in your .env file for better performance.")

# API Helper Functions.
def get_user_info(username):
    url = f"https://api.github.com/users/{username}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 403:
        print(f"{ICON_X} GitHub API returned 403 Forbidden — you might have hit the rate limit.")
        print(f"{ICON_BULB} Try using a token or wait and try again.")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()

def get_followers(username):
    url = f"https://api.github.com/users/{username}/followers"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 403:
        print(f"{ICON_X} GitHub API returned 403 Forbidden — you might have hit the rate limit.")
        print(f"{ICON_BULB} Try using a token or wait and try again.")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()

def get_following(username):
    url = f"https://api.github.com/users/{username}/following"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 403:
        print(f"{ICON_X} GitHub API returned 403 Forbidden — you might have hit the rate limit.")
        print(f"{ICON_BULB} Try using a token or wait and try again.")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()

# Neo4J helper functions.
def add_user(tx, username, url):
    tx.run(
        "MERGE (u:User {username: $username}) "
        "SET u.url = $url",
        username=username, url=url
    )

def add_follow(tx, follower_username, following_username):
    tx.run(
        "MATCH (a:User {username: $follower_username}), (b:User {username: $following_username}) "
        "MERGE (a)-[:FOLLOWS]->(b)",
        follower_username=follower_username, following_username=following_username
    )

# Crawling Logic, which uses Neo4j to store the graph.
def crawl(driver, root_username, max_depth=2, allow_big=False):
    visited = set()

    def _crawl(username, current_depth):
        if username in visited or current_depth > max_depth:
            return

        user_info = get_user_info(username)
        followers_count = user_info.get("followers", 0)

        if followers_count > 100 and not allow_big:
            print(f"{ICON_WARNING} Skipping {username}: has {followers_count} followers (too big without --big flag)")
            return

        print(f"{ICON_CRAWL} Crawling {username} at depth {current_depth} ({followers_count} followers)")

        visited.add(username)
        followers = get_followers(username)
        following = get_following(username)

        with driver.session() as session:
            session.execute_write(add_user, username, f"https://github.com/{username}")

            for f in followers:
                follower_username = f["login"]
                session.execute_write(add_user, follower_username, f["html_url"])
                session.execute_write(add_follow, follower_username, username)

            for f in following:
                following_username = f["login"]
                session.execute_write(add_user, following_username, f["html_url"])
                session.execute_write(add_follow, username, following_username)

        for f in followers:
            _crawl(f["login"], current_depth + 1)

    _crawl(root_username, current_depth=1)

# CLI Options.
def parse_args():
    parser = argparse.ArgumentParser(
        description=f"{ICON_GITHUB} GitHub Social Graph Crawler"
    )
    parser.add_argument(
        "username",
        help="Root GitHub username to crawl"
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=2,
        help="Depth of crawl (default: 2)"
    )
    parser.add_argument(
        "-b",
        "--big",
        action="store_true",
        help="Allow crawling users with more than 100 followers"
    )
    return parser.parse_args()

# Main.
def main():
    check_config()
    args = parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    crawl(driver, args.username, max_depth=args.depth, allow_big=args.big)
    driver.close()

    print(f"{ICON_CHECK} Done!")

if __name__ == "__main__":
    main()

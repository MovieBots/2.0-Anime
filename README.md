# Powerful Anime Telegram Bot (Koyeb Docker)

A beginner-friendly bot starter for anime metadata search and a Telegram video catalog.

## Included
- AniList search with poster, synopsis, year, episode count and score.
- Source-channel media indexing (bot must be admin and receive channel-post updates).
- Optional Gemini thumbnail recognition when caption/filename does not identify a title. This is a guess, not guaranteed; verify ambiguous results.
- Episode + language + quality catalog keys, so 720p/1080p and language versions can coexist; duplicates are skipped.
- Force-subscribe check, episode selection, direct Telegram file delivery using saved `file_id`.
- Premium button menus, poster-based AniList results, group search replies that mention the requesting user.
- Admin-only control panel (`/admin` or `/settings`), protected by an `ADMIN_IDS` allowlist at both command and callback level. Extra admins are configured through comma-separated Telegram numeric user IDs.
- Admin panel shows stats, source-channel status, force-subscribe status, upload instructions and safe configuration status without exposing API keys.
- Dockerfile for Koyeb deployment.

## Caption format (recommended)
Put the anime name first, so recognition is reliable:

```text
Naruto: Shippuden
Episode - 364
Language - Hindi
Quality - 1080p
```

Promotional footer lines and `@channel` mentions are ignored by the parser. If anime name is missing, the optional Gemini image guess is attempted only when Telegram provides a video thumbnail. If it still cannot confidently identify a title, add the title to the caption and repost; do not assume AI recognition is always correct.

## Deploy to Koyeb
1. Create a bot using Telegram `@BotFather`; copy its token.
2. Create a GitHub repository and upload the contents of this folder (files must be at repository root, not nested one folder down).
3. In Koyeb, create an App from that GitHub repo and choose Dockerfile deployment. This is a polling bot, so it does not require an HTTP exposed port.
4. Add environment variables from `.env.example`: `BOT_TOKEN`, `ADMIN_IDS` (comma-separated IDs, e.g. `123456789,987654321`), `SOURCE_CHANNEL_ID`. Configure `FSUB_CHANNELS` and `FSUB_LINKS` if you need force-subscribe. `GEMINI_API_KEY` is optional.
5. Add the bot as administrator in the source channel. Get the numeric channel ID from a trusted Telegram ID bot or your own bot logs. The bot only processes new channel posts after it is running; it does not automatically import old posts.
6. Deploy and inspect Koyeb logs. Do not commit your `.env` or bot token.

## Admin manual upload
Send a video/document to the bot's private chat with caption:

```text
Naruto: Shippuden
Episode - 364
Language - Hindi
Quality - 1080p
```

Your numeric Telegram user ID must be listed in `ADMIN_IDS`. The source channel can use the same caption structure.

## Admin-only security
- Only IDs listed in `ADMIN_IDS` can open the Admin Control Panel or run `/add`, `/stats`, `/admin`, and `/settings`. Admin callback buttons re-check the clicking user ID server-side.
- To add/remove an admin, edit `ADMIN_IDS` in Koyeb Environment Variables and redeploy. Do not share the bot token or Gemini key.
- Group search is available to users, but management commands remain admin-protected.

## Important limitations
- AniList provides metadata and posters, not video files. Videos are delivered only from Telegram file IDs indexed from your source channel or uploaded by an admin.
- Use only media you own or have permission to distribute.
- Force-subscribe requires bot access to check membership in each configured channel. For private channels, ensure IDs/links and bot permissions are configured correctly.
- Gemini API key may incur usage/cost and image recognition may misidentify anime. Without it, title recognition uses caption and filename only.
- Free-hosting availability and persistent storage policies can change. SQLite may be lost if the hosting instance is recreated unless persistent storage is configured. This archive is code-checked, not a claim of a live Koyeb deployment test.

# Copyright and ClipGenie

ClipGenie is built to help you make **original, publishable** clips from videos you have the right to
use. It is a tool, not a legal safeguard.

## What ClipGenie does NOT do

- It does **not** make clips copyright-free. A short clip of someone else's video is still their work.
  Cutting, captions, music, speed changes and cropping do not change who owns the original.
- It does **not** check who owns a video or a song. It records what **you** tell it.
- It does **not** hide anything from YouTube's Content ID or any other copyright system, and it never
  will. It does not remove watermarks or logos.
- It cannot promise that a platform will not flag, claim or remove a clip.

## What ClipGenie does to help

| Step | What happens |
|---|---|
| Choosing a source | You must say whether you own the video, have permission, or it is public domain / licensed for reuse. If you say you are not sure, you get a warning and cannot import from a link. |
| YouTube links | Only after you declare your rights. Public links only, no logins or cookies. |
| Music | Only tracks in your Music library are used. Each track stores its licence, credit text and source. Unknown or incomplete licences show a warning on the track and on every clip that uses it. |
| Before download | A checklist must be completed **for each clip**. Changing the music resets it, because the clip changed. The server enforces this: a clip cannot be downloaded without it. |
| After the checklist | You get a credits text to paste into your video description, and a rights report (JSON) recording the source, the music licence and your confirmations. |

## Your checklist before publishing

1. You own the video, or you have permission or a licence to edit and publish it.
2. The clip has no other people's music, footage, images or logos that you lack rights to. This
   includes music playing in the background of the original recording.
3. The music licence allows your use. For **CC BY** music you must credit the artist: paste the credits
   text into the description. For **royalty-free** music, keep your licence or receipt.
4. You have watched the final clip.

## About the starter music

The five starter tracks are generated from scratch by `backend/tools/make_starter_music.py`. They are
released as CC0 (public domain). They are simple placeholders: add better music you have the rights to.

## About YouTube links

Downloading is done with the open-source `yt-dlp` tool. YouTube's Terms of Service restrict downloading
videos except through features YouTube provides, even for your own videos. If you own the video, the safest
route is to download the original from YouTube Studio and upload the MP4 file instead. Use link import
only if you are comfortable with that.

## This is not legal advice

If you are unsure about a specific video or song, do not publish it, or ask the owner.

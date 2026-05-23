# FenSkeleton – Setup Guide

## What to install (in order)
1. `script.module.cocoscrapers` — from the CocoScrapers repo zip
2. `plugin.video.fenskeleton` — this addon
3. `plugin.video.themoviedb.helper` — TMDbHelper

## Step 1 – First run / sync settings
Open FenSkeleton from Add-ons. It will sync its settings database.
CocoScrapers will be pre-wired automatically.

## Step 2 – Authorize Real-Debrid
Add-ons → FenSkeleton → Configure → Real-Debrid → Authorize
(This opens FenSkeleton's own settings window)

## Step 3 – Configure CocoScrapers torrent providers
Add-ons → FenSkeleton → Configure → External Scrapers → Open CocoScrapers Settings
Enable the torrent providers you want (1337x, Pirate Bay, EZTV for TV, etc.)

## Step 4 – TMDbHelper player
Copy `TMDbHelper_player.json` to:
  .kodi/userdata/addon_data/plugin.video.themoviedb.helper/players/

In TMDbHelper settings → Players:
  Default Movie Player  → FenSkeleton
  Default TV Player     → FenSkeleton

Trakt scrobbles automatically via TMDbHelper.

## That's it
Browse in TMDbHelper, hit play, FenSkeleton scrapes and plays.

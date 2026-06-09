# FenSkeleton - Setup Guide

## What to install (in order)
1. Install a compatible external scraper module, such as CocoScrapers or Magneto
2. `plugin.video.fenskeleton` - this addon
3. `plugin.video.themoviedb.helper` - TMDbHelper

## Step 1 - First run / sync settings
Open FenSkeleton from Add-ons. It will sync its settings database.
Choose your installed external scraper module in FenSkeleton settings.

## Step 2 - Authorize Real-Debrid
Add-ons -> FenSkeleton -> Configure -> Real-Debrid -> Authorize
(This opens FenSkeleton's own settings window)

## Step 3 - Configure external scraper providers
Add-ons -> FenSkeleton -> Configure -> Sources Accounts -> External Scrapers
Choose your installed scraper module, then open its settings and enable the providers you want.

## Step 4 - TMDbHelper player
Copy `TMDbHelper_player.json` to:
  .kodi/userdata/addon_data/plugin.video.themoviedb.helper/players/

In TMDbHelper settings -> Players:
  Default Movie Player  -> FenSkeleton
  Default TV Player     -> FenSkeleton

Trakt scrobbles automatically via TMDbHelper.

## That's it
Browse in TMDbHelper, hit play, FenSkeleton scrapes and plays.
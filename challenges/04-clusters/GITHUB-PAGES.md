# Publishing Day 04 moss clusters on GitHub Pages

The interactive map is a **static Leaflet site**, already accompanied by precomputed NBN Atlas source and cluster GeoJSON. No application server, API key, Vercel or Node runtime is needed for visitors.

## One-off repository setting

The owner of `tomcwxyz/30DayMaps` must enable Pages in the GitHub UI:

1. Visit [30DayMaps → Settings → Pages](https://github.com/tomcwxyz/30DayMaps/settings/pages).
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. The existing workflow `.github/workflows/pages-moss.yml` then publishes the site. If needed, run **Publish Day 04 moss map to GitHub Pages** manually from the **Actions** tab.

After the first successful deployment, the anticipated public address is:

**https://tomcwxyz.github.io/30DayMaps/**

The address is not confirmed live until the Pages deployment completes successfully.

## What the workflow does

- Runs on relevant updates to `web/moss/` on `main`, or manually.
- Checks JavaScript syntax and verifies the NBN source data and real derived cluster features are present, nonempty and internally consistent.
- Copies **only** `web/moss/` to the Pages artifact root, so the homepage is the actual Day 04 map.
- Deploys from the `main` branch through the recommended `github-pages` GitHub Actions environment.
- On pull requests, builds and checks the Pages artifact but does **not** deploy it.

There is no need to duplicate or manually upload a `gh-pages` branch. Future committed changes to the moss map or its source data will trigger automatic redeployments. The source-data regeneration workflow in `.github/workflows/render-moss.yml` is separate from the hosting workflow.

## Important details

- GitHub Pages serves public static files. The NBN Atlas data is already in the public repository, filtered for open licences and aggregated to 10 km grids; no exact wildlife-record locations are published.
- The Leaflet assets and OpenStreetMap basemap tiles are external HTTPS resources and require an internet connection.
- If GitHub Pages has not been enabled in Settings, the deploy step will fail even though the site artifact and checks pass. Only a repository administrator can select the publishing source.
- To change the landing-page route later, adjust the staging directory in `.github/workflows/pages-moss.yml`. Relative paths already work under the `/30DayMaps/` project-site prefix.

# Pokémon TCG Checklist PWA – GitHub Pages versie

Dit pakket zet je Pokémon TCG checklist online als iPhone-klare PWA via GitHub Pages.
De Cardmarket-prijzen worden dagelijks bijgewerkt met GitHub Actions en opgeslagen in `prices.json`.

## Wat zit hierin?

- `index.html` – de app
- `manifest.webmanifest` – PWA-instellingen
- `service-worker.js` – offline cache
- `icons/` – app-iconen en startscherm
- `pokemon_cards_data.json` – kaartdata voor de prijs-koppeling
- `scripts/update_prices.py` – haalt Cardmarket publieke downloadbestanden op en maakt prijsbestanden
- `.github/workflows/update-cardmarket-prices.yml` – dagelijkse automatische update
- `prices.json` – prijsbestand dat de app leest
- `price_history.json` – lokale online prijshistoriek, opgebouwd per dag
- `cardmarket_match_report.csv` – controlebestand voor gekoppelde/niet-gekoppelde kaarten
- `cardmarket_setcodes.csv` – overzicht van Cardmarket-setcodes

## Belangrijk

Je persoonlijke vinkjes, varianten, conditie en notities worden niet in GitHub gezet. Die blijven lokaal op je toestel/browser bewaard. Maak dus in de app regelmatig een backup via **Backup opslaan**.

## Standaard adres van de app

Na publicatie via GitHub Pages wordt je app bereikbaar via:

```text
https://JOUW-GITHUB-GEBRUIKERSNAAM.github.io/pokemon-tcg-checklist/
```

Vervang `JOUW-GITHUB-GEBRUIKERSNAAM` door je eigen GitHub-gebruikersnaam.

## Eerste installatie in het kort

1. Maak op GitHub een nieuwe publieke repository met naam `pokemon-tcg-checklist`.
2. Upload alle bestanden en mappen uit dit pakket naar de repository.
3. Zet GitHub Actions op **Read and write permissions**.
4. Zet GitHub Pages aan via **Settings → Pages → Deploy from a branch → main → /root**.
5. Ga naar **Actions → Update Cardmarket prijzen → Run workflow** om de eerste prijsupdate te starten.
6. Open je GitHub Pages-link op je iPhone in Safari.
7. Kies **Delen → Zet op beginscherm**.

## Prijsupdate

De workflow draait dagelijks rond 04:15 UTC. In België is dat meestal rond 05:15 of 06:15, afhankelijk van zomer-/wintertijd.

Je kan ook manueel updaten via:

**GitHub repository → Actions → Update Cardmarket prijzen → Run workflow**

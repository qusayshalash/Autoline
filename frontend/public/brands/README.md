# Manufacturer logos

Drop a logo here as `<slug>.svg` (or `.png`, see below) and the Statistics dashboard
picks it up on the next page load. Nothing else needs to change.

The slugs come from `src/data/brandRegistry.ts`:

```
toyota  hyundai  kia      mazda      skoda    mitsubishi  nissan   seat
suzuki  renault  subaru   chevrolet  volkswagen  chery    citroen  lexus
honda   ford     audi     fiat       peugeot  mercedes    opel     volvo
daihatsu porsche tesla    isuzu      dacia    geely       chrysler jeep
jaguar  jac      maruti   xpeng      mg       lancia      cupra    dodge
smart   piaggio  gmc      byd        bmw
```

**No logo files ship with the app.** Manufacturer logos are registered trademarks and
are not mine to redistribute, so the dashboard renders a monogram tile in each marque's
own colour instead — which is why it looks complete without them. Add the files yourself
if you have the right to use them.

## Requirements

- **Name**: exactly the slug, lowercase, e.g. `kia.svg`.
- **Format**: SVG is preferred (crisp at any size). PNG works too — see below.
- **Shape**: roughly square artwork with a little padding. The tile renders at 44px on
  the brand card and 22px in the table, and the image is fitted with `object-fit:
  contain`, so nothing is cropped.
- **Background**: transparent. The tile supplies its own surface, and a white rectangle
  baked into the logo shows as a white block in dark mode.

## Using PNG instead of SVG

`brandLogoUrl()` in `src/data/brandRegistry.ts` builds the path. Change the extension
there if you want PNGs:

```ts
export function brandLogoUrl(brand: Brand): string {
  return `/brands/${brand.slug}.png`;
}
```

## Adding a manufacturer

Append an entry to `BRANDS` in `src/data/brandRegistry.ts`. `tokens` is what the value
in the data is matched against — this dataset stores the maker together with its country
of assembly in Hebrew ("קיה קוריאה"), so the token is just the maker half, and Latin
spellings can be listed alongside it.

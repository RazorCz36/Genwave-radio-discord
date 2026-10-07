# GenWave Radio

Oficiální webový přehrávač a **Discord Activity** pro GenWave Radio.

Stream: `https://genwave-radio.com/listen/genwave/radio.mp3` (Icecast / AzuraCast, 192 kbps MP3)

---

## Proč rádio nehrálo – nalezené a opravené chyby

### 1. `index.html` byl utržený uprostřed CSS (hlavní příčina)
Soubor končil na řádku 202 uprostřed deklarace:

```css
        .dots-background-line {
            ...
            filter:        <-- konec souboru
```

Chyběl zbytek CSS, uzavření `</style>`, celé `<body>` a **především jakýkoliv
kód přehrávače**. V repu nebyl žádný `<audio>` element ani JavaScript, který by
stream spustil – přehrávač tedy neměl co přehrát. V celé historii gitu
(commit `ae0312e`) neexistuje žádná úplná verze souboru, nedalo se to vrátit zpět.
→ CSS je doplněné a přehrávač je napsaný celý znovu.

### 2. Discord SDK se vůbec nenačetlo
```html
<script src="https://cdn.jsdelivr.net/npm/@discord/embedded-app-sdk@1"></script>
```
jsDelivr u tohoto balíčku vrací **CommonJS** build (`require('./Discord.cjs')`).
V prohlížeči to spadne na `ReferenceError: require is not defined` – SDK se
nenačte a aktivita nemá handshake s Discordem.
→ SDK se nyní načítá jako **ESM** přes dynamický `import()` z
`@discord/embedded-app-sdk@1.9.0/output/index.mjs`, se záložním `+esm` buildem
a s 4s timeoutem, aby handshake nikdy nezablokoval přehrávání.

### 3. Přímé volání `genwave-radio.com` z aktivity blokuje CSP ⚠️
**Toto je důvod, proč rádio nehrálo konkrétně v Discord aktivitě.**
Aktivita běží v iframe na `https://<APP_ID>.discordsays.com` pod přísným
**Content Security Policy**. Přímý požadavek na nemapovanou externí doménu
skončí chybou `blocked:csp` – a to **i pro `<audio>` a `<img>`**.
Veškerý provoz tedy musí jít přes Discord proxy:

| Venku (GitHub Pages) | Uvnitř Discord aktivity |
|---|---|
| `https://genwave-radio.com/listen/genwave/radio.mp3` | `/.proxy/radio/listen/genwave/radio.mp3` |
| `https://genwave-radio.com/api/nowplaying/genwave` | `/.proxy/radio/api/nowplaying/genwave` |
| `https://genwave-radio.com/api/station/.../art/...jpg` | `/.proxy/radio/api/station/.../art/...jpg` |

Přehrávač to řeší automaticky: podle `location.hostname` pozná, že běží
v aktivitě (`*.discordsays.com`), a všechny URL přepíše na `/.proxy/radio/...`.
Mimo Discord používá přímé URL. Když jeden ze zdrojů selže, zkusí automaticky
druhý.

*Ověřeno naživo:* `https://1556777391337115678.discordsays.com/.proxy/radio/api/nowplaying/genwave`
vrací platná JSON data → mapping `/radio` → `genwave-radio.com` funguje.

### 4. Pozadí `bg.jpg` vs. soubor `BG.JPG`
V CSS bylo `url('bg.jpg')`, ale v repu je `BG.JPG`. GitHub Pages je
**case-sensitive** → obrázek vracel 404.
→ Opraveno na `url('BG.JPG')`.

### 5. Stream je progresivní Icecast, ne HLS
Platforma GenWave má `"hls_enabled": false` – jde o klasický Icecast/Liquidsoap
MP3 stream. Přehrávač proto používá `<audio>` **bez** atributu `crossorigin`
(Icecast neposílá CORS hlavičky a s `crossorigin` by se zvuk nenačetl).

### 6. Chyběl reconnect a ošetření autoplay
Živý stream se čas od času přeruší (restart Icecastu, výpadek sítě) a prohlížeče
blokují autoplay. Přehrávač to teď řeší:
- reconnect s exponenciálním backoffem + cache-buster (`?reconnect=<čas>`),
- watchdog: když 12 s nepřijde zvukový pokrok → reconnect,
- obnova po návratu z pozadí (`visibilitychange`),
- při `NotAllowedError` se zobrazí výzva „Klepni na logo" místo ticha,
- guard na mixed content (stránka `https` + stream `http` = jasná chybová zpráva).

---

## ⚠️ Root mapping v Developer Portalu je potřeba opravit

Při testu proxy vracel root **HTTP 500**:

```
https://1556777391337115678.discordsays.com/            -> HTTP 500
https://1556777391337115678.discordsays.com/index.html  -> HTTP 500
https://1556777391337115678.discordsays.com/BG.JPG      -> HTTP 500
```

Na screenshotu portalu je v *Root Mapping* vidět `razorcz36.github.io/C…`,
ale repo se jmenuje **`Genwave-radio-discord`**. Target musí být přesně:

```
razorcz36.github.io/Genwave-radio-discord/
```

(bez `https://`, s lomítkem na konci). Když je target špatně, Discord proxy
nedokáže stáhnout vstupní HTML a aktivita se nenačte vůbec.

Doporučené nastavení **Activities → URL Mappings**:

| Typ | Prefix | Target |
|---|---|---|
| Root Mapping | `/` | `razorcz36.github.io/Genwave-radio-discord/` |
| Proxy Path Mapping | `/radio` | `genwave-radio.com` |

---

## Konfigurace

Vše se nastavuje v jediném objektu `CONFIG` v `index.html`:

| Konstanta | Význam | Aktuální hodnota |
|---|---|---|
| `STREAM_URL` | URL audio streamu (Icecast mount) | `https://genwave-radio.com/listen/genwave/radio.mp3` |
| `API_URL` | AzuraCast now-playing API | `https://genwave-radio.com/api/nowplaying/genwave` |
| `STREAM_ORIGIN` | Origin, který se přepisuje na proxy | `https://genwave-radio.com` |
| `PROXY_PREFIX` | Prefix z URL Mappings v portalu | `/.proxy/radio` |
| `DISCORD_CLIENT_ID` | Application ID | `1556777391337115678` |
| `METADATA_POLL_MS` | Jak často obnovovat název skladby | 15 s |
| `STALL_TIMEOUT_MS` | Po jaké době ticha obnovit spojení | 12 s |

---

## Nastavení Discord Activity

1. **Developer Portal → General Information**: Application ID `1556777391337115678`
   (je už vložené v `CONFIG.DISCORD_CLIENT_ID`).
2. **Activities → Getting Started**: zapni *Enable Activities*.
3. **Activities → URL Mappings**: viz tabulka výše (root mapping musí mířit na
   `razorcz36.github.io/Genwave-radio-discord/`, proxy mapping `/radio` →
   `genwave-radio.com`).
4. Aplikaci pozvi na server a spusť aktivitu v hlasovém kanálu.

### Důležité: hlavičky při vlastním hostingu
Discord aktivitu vkládá do `<iframe>`. Server, který stránku vydává, **nesmí**
posílat:

```
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
```

GitHub Pages tyto hlavičky neposílá, takže tam funguje bez zásahu. Pokud ale
budeš přehrávač servírovat z **webu GenWave platformy** (`/spectator/*`), narazíš:
platforma stampuje `X-Frame-Options: DENY` + `frame-ancestors 'none'` na všechny
*spectator* routy, a Discord by stránku odmítl vykreslit jako aktivitu.

---

## Omezení, o kterých je dobré vědět

- **Google Fonts uvnitř Discordu**: `@import` na `fonts.googleapis.com` není
  namapovaný, takže CSP ho v aktivitě zablokuje a písma se vykreslí systémovým
  fallbackem. Vzhled to nerozbije; kdybys chtěl i tato písma, musíš si je
  naselfhostovat do repa (a nebo přidat další URL mapping).
- **Mobilní Discord**: audio v aktivitách může být blokované samotnou aplikací.
  Na desktopu (Windows/macOS/Linux) hraje spolehlivě.
- **Autoplay**: v Discord aktivitě se přehrávání obvykle rozjede samo
  (iframe má `allow="autoplay"`). V běžném prohlížeči zvuk spadne až po kliknutí
  na logo – to je chování prohlížeče, ne chyba.
- **Živý stream přes proxy**: Discord proxy propouští chunked odpovědi, ale
  u nekonečného živého streamu to není 100% garantované. Přehrávač proto po
  selhání automaticky zkusí i přímou URL (a naopak).
- **Hlasitost** se ukládá do `localStorage`; v sandboxu bez úložiště se jen nepamatuje.

---

## Struktura

```
index.html   – celý přehrávač (CSS + přehrávač + Discord SDK + proxy logika)
BG.JPG       – pozadí (velká písmena!)
lg.jpg       – logo stanice v kruhovém displeji
```

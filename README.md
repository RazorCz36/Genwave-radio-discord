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

### 3. Pozadí `bg.jpg` vs. soubor `BG.JPG`
V CSS bylo `url('bg.jpg')`, ale v repu je `BG.JPG`. GitHub Pages je
**case-sensitive** → obrázek vracel 404.
→ Opraveno na `url('BG.JPG')`.

### 4. Stream je progresivní Icecast, ne HLS
Platforma GenWave má `"hls_enabled": false` – jde o klasický Icecast/Liquidsoap
MP3 stream. Přehrávač proto používá `<audio>` **bez** atributu `crossorigin`
(Icecast neposílá CORS hlavičky a s `crossorigin` by se zvuk nenačetl).

### 5. Chyběl reconnect a ošetření autoplay
Živý stream se čas od času přeruší (restart Icecastu, výpadek sítě) a prohlížeče
blokují autoplay. Přehrávač to teď řeší:
- reconnect s exponenciálním backoffem + cache-buster (`?reconnect=<čas>`),
- watchdog: když 12 s nepřijde zvukový pokrok → reconnect,
- obnova po návratu z pozadí (`visibilitychange`),
- při `NotAllowedError` se zobrazí výzva „Klepni na logo" místo ticha,
- guard na mixed content (stránka `https` + stream `http` = jasná chybová zpráva).

---

## Konfigurace

Vše se nastavuje v jediném objektu `CONFIG` v `index.html`:

| Konstanta | Význam |
|---|---|
| `STREAM_URL` | URL audio streamu (Icecast mount) |
| `API_URL` | AzuraCast now-playing API (`/api/nowplaying/<shortcode>`) |
| `DISCORD_CLIENT_ID` | **Application ID z Discord Developer Portalu** |
| `METADATA_POLL_MS` | Jak často obnovovat název skladby (15 s) |
| `STALL_TIMEOUT_MS` | Po jaké době ticha obnovit spojení (12 s) |

> ⚠️ `DISCORD_CLIENT_ID` musíš vyplnit, jinak se SDK handshake přeskočí
> (přehrávač funguje dál, ale jako běžný web – bez kontextu Discordu).

Now-playing API posílá `Access-Control-Allow-Origin: *` pro `GET` (výchozí chování
AzuraCastu), takže metadata, obal alba a počet posluchačů fungují i z GitHub Pages.
Když by správce API CORS omezil, přehrávač se tiše přepne na statický název stanice
a **zvuk hraje dál**.

---

## Nastavení Discord Activity

1. **Discord Developer Portal** → *New Application* → zkopíruj **Application ID**
   a vlož ji do `CONFIG.DISCORD_CLIENT_ID`.
2. **Activities → Getting Started**: zapni *Enable Activities*.
3. **Activities → URL Mappings**: přidej mapping `/` →
   `https://razorcz36.github.io/Genwave-radio-discord/`
   (nebo nech prázdné a použij přímou URL).
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
Stránka proto musí být hostovaná tam, kde se framing nezakazuje.

---

## Omezení, o kterých je dobré vědět

- **Mobilní Discord**: audio v aktivitách může být zablokované samotnou aplikací.
  Na desktopu (Windows/macOS/Linux) hraje spolehlivě.
- **Autoplay**: v Discord aktivitě se přehrávání obvykle rozjede samo
  (iframe má `allow="autoplay"`). V běžném prohlížeči zvuk spadne až po kliknutí
  na logo – to je chování prohlížeče, ne chyba.
- **Hlasitost** se ukládá do `localStorage`; v sandboxu bez úložiště se jen nepamatuje.

---

## Struktura

```
index.html   – celý přehrávač (CSS + přehrávač + Discord SDK)
BG.JPG       – pozadí (velká písmena!)
lg.jpg       – logo stanice v kruhovém displeji
```

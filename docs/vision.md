# Tekken 3 Character Builder – De ultieme app

De levende versie staat in het Claude-document; dit is een momentopname.

## Visie

De ultieme app laat iedereen zijn eigen personage in Tekken 3 zetten: van uiterlijk en portret tot vechtstijl, losse moves en uiteindelijk eigen modellen en animaties. Denk aan de creatiemodus van de WWE-games en Soul Calibur, maar dan voor een PS1-klassieker.

- **Laagdrempelig:** een nieuwkomer heeft binnen een paar minuten een speelbaar personage.
- **Diepgaand:** wie wil, kan tot op de move nauwkeurig tweaken.
- **Eigen werk:** personages zijn pakketjes met eigen content, nooit bestanden uit het spel.
- **Stijl:** een moderne app die zwaar leunt op de look van Tekken 3 en de PS1.

## De drie lagen van creatie

1. **Stijl kiezen (Soul Calibur):** een vechtstijl geeft in één keer een complete moveset (het donorsysteem), later ook TTT-movesets.
2. **Moves verzamelen (TTT2 Combot):** per knopcombinatie moves uit andere movesets toewijzen.
3. **Blokkenschema (M.U.G.E.N):** strings en combo's bouwen; hier landen ook eigen animaties.

## Uiterlijk

- **Paletten:** kostuumkleuren via de PS1-kleurpaletten.
- **Portret en naam:** foto wordt selectieportret plus rastertegels; naambordje uit het Tekken 3-lettertype.
- **Eigen 3D-model:** verkleinen tot PS1-budget, opknippen per bot, textures naar PS1-kleuren.
- **Riggen:** skelet van AI-tools koppelen aan het Tekken 3-skelet.

## Eigen animaties

Pose-editor met sleutelhoudingen (aanloop, raakmoment, herstel), tijdlijn, raakmoment markeren, importeren als alternatief. Geïnspireerd door Fighter Maker op de PS1. Idee: twee skeletten (aanvaller en tegenstander) voor worpen, bereik en reacties.

## AI-animaties

Text-to-motion levert skeletanimaties (QuickMagic, PINOC, onderzoeksdataset AnimationGPT, video-mocap). De app zet ze om: Tekken 3-skelet, PS1-framerate, timing aanscherpen, begin en eind in vechthouding, raakmoment bepalen, bijschaven, eerlijkheidscheck.

## Presentatie, sjablonen en testlus

Sjabloonpersonages, intro/winpose/stem/stage/muziek, tutorial, testknop overal, live balansfeedback.

## Eerlijkheidscheck

Originele cast als meetlat; verkeerslicht per onderdeel (snelheid, lanceringen, schade, straf-risico, lows); Fair of Just for fun; status gaat mee in gedeelde pakketten.

## Delen en bibliotheek

`.t3char`-pakketten, veilig importeren (alleen data), delen via modsites, compatibiliteit per versie.

## Extra ideeën

Accessoires, lichaamsverhoudingen, CPU-persoonlijkheid, rivaal en eindbaas, command list en combotraining, meerdere kostuums, eigen stem, deelcode, "verras me".

## Technische routekaart

| Stap | Wat het oplevert | Haalbaarheid |
| --- | --- | --- |
| 1. CUSTOM-pagina testen en afronden | Eigen personages met portret en naam in Expanded | Gebouwd, test volgt |
| 2. Stijlen en complete movesets | Soul Calibur-laag, inclusief TTT-movesets | Hoog |
| 3. Paletten | Eigen kleuren op elk kostuum | Hoog |
| 4. Presentatie, sjablonen, testknop | Intro, winpose, stem, startpunten | Middel tot hoog |
| 5. Moves verzamelen (Combot) | Losse moves op eigen knoppen | Middel |
| 6. Eerlijkheidscheck | Verkeerslicht per personage | Middel |
| 7. Eigen 3D-modellen en riggen | Volledig eigen uiterlijk | Middel |
| 8. Blokkenschema | Strings en combo's zelf bouwen | Lager |
| 9. Pose-editor en eigen animaties | Compleet nieuwe moves | Laagst |

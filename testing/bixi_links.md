# BIXI Comparison Links

Companion to `routes.json` / `addresses.md`, for the manual "Google BIXI" leg of the
3-way comparison (Trip Planner / Google Transit / Google BIXI) -- see
`testing/google_compare.py`'s module docstring for why this can't be automated:
Google's developer Routes API has no bikeshare mode, only the consumer Maps app/website
does (in select cities, including Montreal). Click through, switch to Google's bike-share
option if offered, and read off the distance/time.

Regenerate with: `python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'testing'); from google_compare import bixi_maps_link" ...` or simply rerun the snippet that produced this file.

## Route #1 -- sanity, walk
**1000 rue de la Gauchetière O** (Downtown) -> **Centre Bell** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4984%2C-73.5667&destination=45.4961%2C-73.5693&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4984%2C-73.5667&destination=45.4961%2C-73.5693&travelmode=bicycling)


## Route #2 -- bixi, walk
**Peel Basin (Griffintown)** (Griffintown) -> **Marché Atwater** (Saint-Henri)

[https://www.google.com/maps/dir/?api=1&origin=45.4919%2C-73.556&destination=45.4832%2C-73.5788&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4919%2C-73.556&destination=45.4832%2C-73.5788&travelmode=bicycling)


## Route #3 -- metro, bixi
**Guy & Sainte-Catherine** (Downtown) -> **Marché Bonsecours** (Old Montreal)

[https://www.google.com/maps/dir/?api=1&origin=45.4949%2C-73.5789&destination=45.5093%2C-73.5534&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4949%2C-73.5789&destination=45.5093%2C-73.5534&travelmode=bicycling)


## Route #4 -- bixi, bus
**Parc La Fontaine** (Plateau-Mont-Royal) -> **Rue Bernard & Ave du Parc** (Mile End)

[https://www.google.com/maps/dir/?api=1&origin=45.5259%2C-73.5701&destination=45.5219%2C-73.6013&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5259%2C-73.5701&destination=45.5219%2C-73.6013&travelmode=bicycling)


## Route #5 -- bus, metro
**Beaubien & Saint-Denis** (Rosemont–La Petite-Patrie) -> **Laurier metro** (Plateau-Mont-Royal)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #6 -- metro, baseline
**Côte-des-Neiges & Queen-Mary** (Côte-des-Neiges) -> **Jean-Talon metro** (Villeray)

[https://www.google.com/maps/dir/?api=1&origin=45.4939%2C-73.6229&destination=45.5411%2C-73.6136&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4939%2C-73.6229&destination=45.5411%2C-73.6136&travelmode=bicycling)


## Route #7 -- bus, bixi
**Monkland Village** (NDG) -> **Cavendish Mall** (Côte-Saint-Luc)

[https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.478%2C-73.6438&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.478%2C-73.6438&travelmode=bicycling)


## Route #8 -- bixi
**Verdun Beach (Plage de l'Horloge)** (Verdun) -> **Marché Atwater** (Saint-Henri)

[https://www.google.com/maps/dir/?api=1&origin=45.4494%2C-73.5714&destination=45.4832%2C-73.5788&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4494%2C-73.5714&destination=45.4832%2C-73.5788&travelmode=bicycling)


## Route #9 -- metro
**Angrignon metro / Park** (LaSalle) -> **Marché Atwater** (Saint-Henri)

[https://www.google.com/maps/dir/?api=1&origin=45.4462%2C-73.6035&destination=45.4832%2C-73.5788&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4462%2C-73.6035&destination=45.4832%2C-73.5788&travelmode=bicycling)


## Route #10 -- rem, bridge, bixi
**Verdun metro** (Verdun) -> **Brossard REM terminus** (Brossard (South Shore))

[https://www.google.com/maps/dir/?api=1&origin=45.4587%2C-73.5679&destination=45.4381%2C-73.4306&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4587%2C-73.5679&destination=45.4381%2C-73.4306&travelmode=bicycling)


## Route #11 -- rem
**Île-des-Sœurs REM station** (Nun's Island) -> **Gare Centrale** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4703%2C-73.5389&destination=45.5%2C-73.567&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4703%2C-73.5389&destination=45.5%2C-73.567&travelmode=bicycling)


## Route #12 -- rem, south-shore
**Brossard REM terminus** (Brossard (South Shore)) -> **McGill University** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4381%2C-73.4306&destination=45.5048%2C-73.5772&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4381%2C-73.4306&destination=45.5048%2C-73.5772&travelmode=bicycling)


## Route #13 -- metro, south-shore
**Longueuil–Université-de-Sherbrooke metro** (Longueuil (South Shore)) -> **Berri-UQAM metro** (Downtown/Plateau)

[https://www.google.com/maps/dir/?api=1&origin=45.5257%2C-73.5217&destination=45.5152%2C-73.5605&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5257%2C-73.5217&destination=45.5152%2C-73.5605&travelmode=bicycling)


## Route #14 -- metro, baseline
**Côte-Vertu metro** (Saint-Laurent) -> **Honoré-Beaugrand metro** (Mercier)

[https://www.google.com/maps/dir/?api=1&origin=45.5145%2C-73.6875&destination=45.5978%2C-73.533&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5145%2C-73.6875&destination=45.5978%2C-73.533&travelmode=bicycling)


## Route #15 -- metro
**Jean-Talon Market** (Villeray) -> **Berri-UQAM metro** (Downtown/Plateau)

[https://www.google.com/maps/dir/?api=1&origin=45.5367%2C-73.6151&destination=45.5152%2C-73.5605&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5367%2C-73.6151&destination=45.5152%2C-73.5605&travelmode=bicycling)


## Route #16 -- metro, bixi
**Beaubien & Saint-Hubert** (Rosemont–La Petite-Patrie) -> **Chinatown (rue de la Gauchetière)** (Chinatown)

[https://www.google.com/maps/dir/?api=1&origin=45.5407%2C-73.6006&destination=45.5061%2C-73.5605&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5407%2C-73.6006&destination=45.5061%2C-73.5605&travelmode=bicycling)


## Route #17 -- bus
**Marché Central** (Ahuntsic-Cartierville) -> **Parc Jarry** (Villeray)

[https://www.google.com/maps/dir/?api=1&origin=45.5299%2C-73.6669&destination=45.5363%2C-73.6265&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5299%2C-73.6669&destination=45.5363%2C-73.6265&travelmode=bicycling)


## Route #18 -- bus, sparse
**Henri-Bourassa metro** (Ahuntsic-Cartierville) -> **Henri-Bourassa E & Léger** (Montréal-Nord)

[https://www.google.com/maps/dir/?api=1&origin=45.5546%2C-73.6693&destination=45.589%2C-73.63&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5546%2C-73.6693&destination=45.589%2C-73.63&travelmode=bicycling)


## Route #19 -- bus, metro
**Langelier & Jean-Talon E** (Saint-Léonard) -> **Peel metro** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.588%2C-73.5836&destination=45.4998%2C-73.5751&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.588%2C-73.5836&destination=45.4998%2C-73.5751&travelmode=bicycling)


## Route #21 -- bus, sparse
**RDP Library (boul. Perras)** (Rivière-des-Prairies) -> **Anjou metro area** (Anjou)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #22 -- walk, bixi
**Parc Outremont** (Outremont) -> **Rue Bernard & Ave du Parc** (Mile End)

[https://www.google.com/maps/dir/?api=1&origin=45.5188%2C-73.6096&destination=45.5219%2C-73.6013&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5188%2C-73.6096&destination=45.5219%2C-73.6013&travelmode=bicycling)


## Route #23 -- walk, bus
**Université de Montréal** (Côte-des-Neiges/Outremont) -> **Jean-Talon Market** (Villeray)

[https://www.google.com/maps/dir/?api=1&origin=45.5048%2C-73.6142&destination=45.5367%2C-73.6151&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5048%2C-73.6142&destination=45.5367%2C-73.6151&travelmode=bicycling)


## Route #24 -- ebike, hilly
**Beaver Lake, Parc du Mont-Royal** (Plateau/Outremont) -> **Vieux-Port de Montréal** (Old Montreal)

[https://www.google.com/maps/dir/?api=1&origin=45.5058%2C-73.5959&destination=45.5075%2C-73.554&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5058%2C-73.5959&destination=45.5075%2C-73.554&travelmode=bicycling)


## Route #25 -- sparse, edge
**Pointe-Claire Village** (Pointe-Claire (West Island)) -> **Fairview Pointe-Claire** (Pointe-Claire (West Island))

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #26 -- bus, edge
**Kirkland Recreation Centre** (Kirkland (West Island)) -> **Lionel-Groulx metro** (Saint-Henri)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #27 -- bus, metro, edge
**Pierrefonds–Roxboro station** (Pierrefonds-Roxboro) -> **Gare Centrale** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4972%2C-73.85&destination=45.5%2C-73.567&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4972%2C-73.85&destination=45.5%2C-73.567&travelmode=bicycling)


## Route #28 -- walk, sanity
**Place Jacques-Cartier** (Old Montreal) -> **rue de la Gauchetière (Chinatown)** (Chinatown)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #29 -- bus, metro
**Chinatown (rue de la Gauchetière)** (Chinatown) -> **Little Italy (Jean-Talon & St-Laurent)** (Villeray/Rosemont)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #30 -- bus, metro
**Complexe Desjardins** (Downtown) -> **Galeries d'Anjou** (Anjou)

[https://www.google.com/maps/dir/?api=1&origin=45.5083%2C-73.5644&destination=45.6089%2C-73.5595&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5083%2C-73.5644&destination=45.6089%2C-73.5595&travelmode=bicycling)


## Route #31 -- bus, known-corridor
**Concordia SGW (1455 de Maisonneuve O)** (Downtown) -> **Concordia Loyola (7141 Sherbrooke O)** (NDG)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #32 -- night, frequency, bus
**Saint-Laurent & Mont-Royal** (Plateau-Mont-Royal) -> **Jean-Talon Market** (Villeray)

[https://www.google.com/maps/dir/?api=1&origin=45.5225%2C-73.5793&destination=45.5367%2C-73.6151&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5225%2C-73.5793&destination=45.5367%2C-73.6151&travelmode=bicycling)


## Route #33 -- rush-hour
**Monkland Village** (NDG) -> **Peel metro** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.4998%2C-73.5751&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.4998%2C-73.5751&travelmode=bicycling)


## Route #34 -- off-peak
**Monkland Village** (NDG) -> **Peel metro** (Downtown)

[https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.4998%2C-73.5751&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.4675%2C-73.6151&destination=45.4998%2C-73.5751&travelmode=bicycling)


## Route #35 -- bus, baseline, bridge
**Downtown (Peel / Ste-Catherine)** (Downtown) -> **Casino de Montréal** (Parc Jean-Drapeau)

[https://www.google.com/maps/dir/?api=1&origin=45.5017%2C-73.5715&destination=45.5055%2C-73.5258&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5017%2C-73.5715&destination=45.5055%2C-73.5258&travelmode=bicycling)


## Route #36 -- late-night-closure
**Saint-Denis & Mont-Royal** (Plateau-Mont-Royal) -> **Wellington & de l'Église** (Verdun)

_bixi not allowed for this route (allowedModes.bixi = false) -- no comparison applicable._


## Route #37 -- late-night-closure, bus
**Peel & Ste-Catherine** (Downtown) -> **Henri-Bourassa metro** (Ahuntsic-Cartierville)

[https://www.google.com/maps/dir/?api=1&origin=45.5017%2C-73.5715&destination=45.5546%2C-73.6693&travelmode=bicycling](https://www.google.com/maps/dir/?api=1&origin=45.5017%2C-73.5715&destination=45.5546%2C-73.6693&travelmode=bicycling)

# Route Addresses for Google Maps Comparison

Companion to `routes.json`, for manually pasting into Google Maps to fill in the
Route Validation Log's Google Maps column. For each point: the label/neighborhood
(as in routes.json), an address or description to search, and the exact lat/lon
pinned in routes.json.

Some points have no real civic address (parks, paths, basins, bare intersections,
or deliberately generic placeholders like "Residential address, Rosemont") — those
are labeled honestly instead of showing a misleading nearby street name. For named
landmarks (stations, Gare Centrale, Casino de Montréal, etc.) the address shown is
the landmark's own verified address, not just the nearest road to the pin.

**Corrected this pass:**
- Route 1 origin was ~85m off, on Rue Mansfield (a parking lot) instead of Rue de La Gauchetière.
- Route 35 destination (Casino de Montréal) was ~1.2km off — pinned on Île Sainte-Hélène instead of Île Notre-Dame, where the casino actually is.
- Routes 10/11's Île-des-Sœurs REM station point was ~790m off from the real station.

## Route #1 -- sanity, walk
*Same-block sanity check -- two points ~600m apart, same neighborhood. Expect a walk-only itinerary and near-zero time delta vs. Google Maps.*

**FROM: 1000 rue de la Gauchetière O**
Downtown
1000 Rue de La Gauchetière O, Montréal, QC H3A 4W5
Coordinates: 45.4984, -73.5667

**TO: Centre Bell**
Downtown
1288 Avenue des Canadiens-de-Montréal, Montréal, QC H3B 0G6
Coordinates: 45.4961, -73.5693


## Route #2 -- bixi, walk
*Short hop between adjacent boroughs -- good candidate for a walk vs. BIXI comparison.*

**FROM: Peel Basin (Griffintown)**
Griffintown
No civic address — Peel Basin waterfront, Griffintown
Coordinates: 45.4919, -73.556

**TO: Marché Atwater**
Saint-Henri
2650 Avenue Lionel-Groulx, Montréal, QC H3J 2H7
Coordinates: 45.4832, -73.5788


## Route #3 -- walk, bus
*Dense downtown-to-Old-Montreal tourist corridor, medium walk or short bus.*

**FROM: McGill University (845 Sherbrooke O)**
Downtown
845 Rue Sherbrooke O, Montréal, QC H3A 0G4
Coordinates: 45.5048, -73.5772

**TO: Vieux-Port de Montréal**
Old Montreal
443 Rue Saint-Vincent, Montréal, QC H2Y 3B3
Coordinates: 45.5075, -73.554


## Route #4 -- bixi
*Classic BIXI commute between two dense, bike-friendly boroughs.*

**FROM: Parc La Fontaine**
Plateau-Mont-Royal
No civic address — inside Parc La Fontaine
Coordinates: 45.5259, -73.5701

**TO: Rue Bernard & Ave du Parc**
Mile End
Intersection of Rue Bernard & Avenue du Parc, Montréal, QC H2V 4G7
Coordinates: 45.5219, -73.6013


## Route #5 -- sanity, metro
*Single-stop, metro-only sanity check (Orange line, one hop).*

**FROM: Mont-Royal metro**
Plateau-Mont-Royal
465 Avenue du Mont-Royal E, Montréal, QC H2J 1W3
Coordinates: 45.5247, -73.5824

**TO: Laurier metro**
Plateau-Mont-Royal
755 Boulevard Saint-Joseph E, Montréal, QC H2J 1N7
Coordinates: 45.5279, -73.5865


## Route #6 -- metro, bus, baseline
*Reuses a known perf-testing baseline route -- good cross-reference point for timing.*

**FROM: Côte-des-Neiges & Queen-Mary**
Côte-des-Neiges
Intersection of Côte-des-Neiges & Queen-Mary, Montréal, QC H3T 1P1
Coordinates: 45.4939, -73.6229

**TO: Bonaventure metro**
Downtown
1025 Rue Saint-Jacques, Montréal, QC H3C 1G8
Coordinates: 45.4967, -73.5661


## Route #7 -- walk, bus
*Short hybrid trip through low-density, affluent boroughs.*

**FROM: Monkland Village**
NDG
2144 Avenue de Clifton, Montréal, QC H4A 2A1
Coordinates: 45.4675, -73.6151

**TO: Westmount Park**
Westmount
15 Avenue Springfield, Montréal, QC H3Y 2J2
Coordinates: 45.4841, -73.5993


## Route #8 -- bixi
*BIXI along the Lachine Canal path -- tests OSRM bike routing on a dedicated bike corridor.*

**FROM: Verdun Beach (Plage de l'Horloge)**
Verdun
427 Rue Manning, Montréal, QC H4H 2B3
Coordinates: 45.4494, -73.5714

**TO: Marché Atwater**
Saint-Henri
2650 Avenue Lionel-Groulx, Montréal, QC H3J 2H7
Coordinates: 45.4832, -73.5788


## Route #9 -- bus, walk
*Bus + walk in lower-density southwest boroughs, sparser transit grid.*

**FROM: Angrignon metro / Park**
LaSalle
3500 Boulevard des Trinitaires, Montréal, QC H8N 0G2
Coordinates: 45.4462, -73.6035

**TO: Lachine Canal (Lachine)**
Lachine
450 6e Avenue, Montréal, QC H8S 1W4
Coordinates: 45.4386, -73.6693


## Route #10 -- rem, bridge
*REM test across a bridge crossing -- check the app picks up the REM branch correctly.*

**FROM: Verdun metro**
Verdun
265 1re Avenue, Montréal, QC H4G 1X1
Coordinates: 45.4587, -73.5679

**TO: Île-des-Sœurs REM station** _(coordinate corrected)_
Nun's Island
Station Île-des-Sœurs (REM), Autoroute 15, Verdun, Montréal, QC H3E 3B3
Coordinates: 45.4703, -73.5389


## Route #11 -- rem
*Full REM segment into the downtown terminus.*

**FROM: Île-des-Sœurs REM station** _(coordinate corrected)_
Nun's Island
Station Île-des-Sœurs (REM), Autoroute 15, Verdun, Montréal, QC H3E 3B3
Coordinates: 45.4703, -73.5389

**TO: Gare Centrale**
Downtown
895 Rue de La Gauchetière O, Montréal, QC H5A 1L3 (Gare Centrale)
Coordinates: 45.5, -73.567


## Route #12 -- rem, south-shore
*Cross-river REM commute from the real South Shore terminus (Station Brossard) into downtown.*

**FROM: Brossard REM terminus**
Brossard (South Shore)
Station Brossard (REM terminus), Boulevard de Rome, Brossard, QC J4Z 3H8
Coordinates: 45.4381, -73.4306

**TO: McGill University**
Downtown
845 Rue Sherbrooke O, Montréal, QC H3A 0G4
Coordinates: 45.5048, -73.5772


## Route #13 -- metro, south-shore
*Yellow line into the Orange/Green interchange -- also exercises the <20m correspondance-transfer fix at Berri-UQAM.*

**FROM: Longueuil–Université-de-Sherbrooke metro**
Longueuil (South Shore)
101 Place Charles-Le Moyne, Montréal, QC J4K 2T3
Coordinates: 45.5257, -73.5217

**TO: Berri-UQAM metro**
Downtown/Plateau
Station Berri-UQAM, Rue Berri, Montréal, QC H2L 0B1
Coordinates: 45.5152, -73.5605


## Route #14 -- metro, baseline
*Known cross-island metro-only baseline route -- good timing cross-reference (multiple transfers).*

**FROM: Côte-Vertu metro**
Saint-Laurent
1205 Rue Cardinal, Montréal, QC H4L 1R1
Coordinates: 45.5145, -73.6875

**TO: Honoré-Beaugrand metro**
Mercier
8101 Rue Gustave Bleau, Montréal, QC H1L 1H4
Coordinates: 45.5978, -73.533


## Route #15 -- bus
*Bus-heavy trip between adjacent central boroughs.*

**FROM: Jean-Talon Market**
Villeray
7070 Avenue Henri-Julien, Montréal, QC H2S 1L6
Coordinates: 45.5367, -73.6151

**TO: Plaza Saint-Hubert**
Rosemont–La Petite-Patrie
6230 Rue Saint-Hubert, Montréal, QC H2S 1S7
Coordinates: 45.5348, -73.6006


## Route #16 -- bus, metro
*Bus/metro combo into a major event venue area.*

**FROM: Beaubien & Saint-Hubert**
Rosemont–La Petite-Patrie
6561 Rue Chambord, Montréal, QC H2S 2B8
Coordinates: 45.5407, -73.6006

**TO: Olympic Stadium / Stade Saputo**
Hochelaga-Maisonneuve
4545 Avenue Pierre-De Coubertin, Montréal, QC H1V 1A6
Coordinates: 45.5579, -73.5515


## Route #17 -- bus
*North-borough bus corridor, moderate density.*

**FROM: Marché Central**
Ahuntsic-Cartierville
90 Place de la Côte-Vertu, Montréal, QC H4N 1C0
Coordinates: 45.5299, -73.6669

**TO: Parc Jarry**
Villeray
No civic address — inside Parc Jarry
Coordinates: 45.5363, -73.6265


## Route #18 -- bus, sparse
*Bus-heavy north-end trip into a borough with sparse metro coverage.*

**FROM: Henri-Bourassa metro**
Ahuntsic-Cartierville
10738 Rue Berri, Montréal, QC H3L 2H3
Coordinates: 45.5546, -73.6693

**TO: Henri-Bourassa E & Léger**
Montréal-Nord
10388 Avenue Pelletier, Montréal, QC H1H 4A8
Coordinates: 45.589, -73.63


## Route #19 -- bus, metro
*Long commute from an underserved borough -- bus into metro trunk line.*

**FROM: Langelier & Jean-Talon E**
Saint-Léonard
5956 Boulevard Métropolitain - Voie de desserte S, Montréal, QC H1P 1X3
Coordinates: 45.588, -73.5836

**TO: Peel metro**
Downtown
1200 Boulevard De Maisonneuve O, Montréal, QC H3A 1N6
Coordinates: 45.4998, -73.5751


## Route #21 -- bus, sparse
*Far east-end periphery -- tests behavior in the sparsest-transit part of the coverage area.*

**FROM: RDP Library (boul. Perras)**
Rivière-des-Prairies
12225 Rue Sherbrooke E, Montréal, QC H1B 1C8
Coordinates: 45.646, -73.515

**TO: Anjou metro area**
Anjou
Approximate area (no single civic address) — Rue du Trianon, Anjou, QC H1N 1E9
Coordinates: 45.5915, -73.5445


## Route #22 -- walk, bixi
*Short walk/BIXI hop between adjacent affluent boroughs.*

**FROM: Parc Outremont**
Outremont
1320 Avenue Bernard, Montréal, QC H2V 1W1
Coordinates: 45.5188, -73.6096

**TO: Rue Bernard & Ave du Parc**
Mile End
Intersection of Rue Bernard & Avenue du Parc, Montréal, QC H2V 4G7
Coordinates: 45.5219, -73.6013


## Route #23 -- walk, bus
*Hilltop campus start -- Mount Royal terrain affects walking/biking time estimates.*

**FROM: Université de Montréal**
Côte-des-Neiges/Outremont
2700 Chemin de l'Est, Montréal, QC H3T 1J4
Coordinates: 45.5048, -73.6142

**TO: Jean-Talon Market**
Villeray
7070 Avenue Henri-Julien, Montréal, QC H2S 1L6
Coordinates: 45.5367, -73.6151


## Route #24 -- ebike, hilly
*Force e-bike mode on a hilly route -- compare against regular BIXI to sanity-check the e-bike assist modeling.*

**FROM: Beaver Lake, Parc du Mont-Royal**
Plateau/Outremont
No civic address — path near Lac aux Castors, Parc du Mont-Royal
Coordinates: 45.5058, -73.5959

**TO: Vieux-Port de Montréal**
Old Montreal
443 Rue Saint-Vincent, Montréal, QC H2Y 3B3
Coordinates: 45.5075, -73.554


## Route #25 -- sparse, edge
*Short local trip in a low-density suburb -- tests behavior near the edge of the service area bounds.*

**FROM: Pointe-Claire Village**
Pointe-Claire (West Island)
Approximate area (no single civic address) — Avenue Duke-of-Kent, Pointe-Claire, QC H9R 3J2
Coordinates: 45.4515, -73.8171

**TO: Fairview Pointe-Claire**
Pointe-Claire (West Island)
120 Avenue Alston, Montréal, QC H9R 0G1
Coordinates: 45.4547, -73.8267


## Route #26 -- bus, edge
*Long peripheral commute, bus into the metro trunk -- stresses the edge of the map bounds.*

**FROM: Kirkland Recreation Centre**
Kirkland (West Island)
34 Rue Vincent-Blouin, Montréal, QC H9J 2Y3
Coordinates: 45.4477, -73.8737

**TO: Lionel-Groulx metro**
Saint-Henri
2744 Rue Workman, Montréal, QC H4C 1N9
Coordinates: 45.482, -73.5779


## Route #27 -- bus, metro, edge
*Commuter-rail-adjacent West Island trip, likely bus+metro fallback if exo/REM isn't in scope.*

**FROM: Pierrefonds–Roxboro station**
Pierrefonds-Roxboro
13899 Boulevard Gouin O, Montréal, QC H8Z 1X7
Coordinates: 45.4972, -73.85

**TO: Gare Centrale**
Downtown
895 Rue de La Gauchetière O, Montréal, QC H5A 1L3 (Gare Centrale)
Coordinates: 45.5, -73.567


## Route #28 -- walk, sanity
*Short tourist-corridor walk through the dense downtown grid.*

**FROM: Place Jacques-Cartier**
Old Montreal
275 Rue Notre-Dame E, Montréal, QC H2Y 3B3
Coordinates: 45.5088, -73.5537

**TO: rue de la Gauchetière (Chinatown)**
Chinatown
Rue de La Gauchetière O, Quartier chinois, Montréal, QC H2Z 1C1
Coordinates: 45.5061, -73.5605


## Route #29 -- bus, metro
*North-south cross-town trip, mixed bus/metro.*

**FROM: Chinatown (rue de la Gauchetière)**
Chinatown
Rue de La Gauchetière O, Quartier chinois, Montréal, QC H2Z 1C1
Coordinates: 45.5061, -73.5605

**TO: Little Italy (Jean-Talon & St-Laurent)**
Villeray/Rosemont
7070 Avenue Henri-Julien, Montréal, QC H2S 1L6
Coordinates: 45.5367, -73.6151


## Route #30 -- bus, metro
*Long cross-town errand-style trip, downtown to the east end.*

**FROM: Complexe Desjardins**
Downtown
150 Rue Sainte-Catherine O, Montréal, QC H2X 3Y2
Coordinates: 45.5083, -73.5644

**TO: Galeries d'Anjou**
Anjou
7755 Place Pocé, Montréal, QC H1K 1C1
Coordinates: 45.6089, -73.5595


## Route #31 -- bus, known-corridor
*Real shuttle-route corridor -- Concordia's own published shuttle time is a third data point beyond Google Maps.*

**FROM: Concordia SGW (1455 de Maisonneuve O)**
Downtown
1455 Boulevard De Maisonneuve O, Montréal, QC H3G 1M8
Coordinates: 45.4966, -73.5789

**TO: Concordia Loyola (7141 Sherbrooke O)**
NDG
7141 Rue Sherbrooke O, Montréal, QC H4B 1R6
Coordinates: 45.4585, -73.6398


## Route #32 -- night, frequency
*Run at ~1:00 AM weekend -- tests last-metro/bus frequency handling versus Google's own late-night schedule awareness (metro is still running at this hour on Fri/Sat).*

**FROM: Saint-Laurent & Mont-Royal**
Plateau-Mont-Royal
4279 Rue Saint-Denis, Montréal, QC H2J 2K9
Coordinates: 45.5225, -73.5793

**TO: Residential address, Rosemont**
Rosemont–La Petite-Patrie
Approximate placeholder point (no single civic address) — Rue Masson, Montréal, QC H2G 2E4
Coordinates: 45.5423, -73.5789


## Route #33 -- rush-hour
*Run at 8:00 AM weekday -- pair with #34 to compare rush-hour behavior.*

**FROM: Monkland Village**
NDG
2144 Avenue de Clifton, Montréal, QC H4A 2A1
Coordinates: 45.4675, -73.6151

**TO: Peel metro**
Downtown
1200 Boulevard De Maisonneuve O, Montréal, QC H3A 1N6
Coordinates: 45.4998, -73.5751


## Route #34 -- off-peak
*Same pair as #33, run at 2:00 PM weekday -- isolates schedule/frequency sensitivity from the route choice itself.*

**FROM: Monkland Village**
NDG
2144 Avenue de Clifton, Montréal, QC H4A 2A1
Coordinates: 45.4675, -73.6151

**TO: Peel metro**
Downtown
1200 Boulevard De Maisonneuve O, Montréal, QC H3A 1N6
Coordinates: 45.4998, -73.5751


## Route #35 -- bus, baseline, bridge
*Reuses a known perf-testing baseline route -- island-hopping via bridge, bus-heavy, good timing cross-reference.*

**FROM: Downtown (Peel / Ste-Catherine)**
Downtown
Intersection of Rue Peel & Rue Sainte-Catherine O, Montréal, QC H3B 4W3
Coordinates: 45.5017, -73.5715

**TO: Casino de Montréal** _(coordinate corrected)_
Parc Jean-Drapeau
1 Avenue du Casino, Montréal, QC H3C 4W7 (Casino de Montréal)
Coordinates: 45.5055, -73.5258


## Route #36 -- late-night-closure
*Run at 2:30 AM weekday -- metro and REM are closed; checks that the app falls back to the night bus network (or walk/BIXI) instead of erroring or silently offering a metro leg that doesn't actually run.*

**FROM: Saint-Denis & Mont-Royal**
Plateau-Mont-Royal
4407 Rue Rivard, Montréal, QC H2J 2A2
Coordinates: 45.5241, -73.5809

**TO: Wellington & de l'Église**
Verdun
377 1re Avenue, Montréal, QC H4G 1X1
Coordinates: 45.4589, -73.5697


## Route #37 -- late-night-closure
*Run at 3:00 AM weekday -- same closure check as #36 on a shorter, more central pair where a night-bus or walk fallback should be easy to find if one exists.*

**FROM: Peel & Ste-Catherine**
Downtown
Rue Mansfield, Montréal, QC H3B 4W3
Coordinates: 45.5017, -73.5715

**TO: Côte-des-Neiges & Queen-Mary**
Côte-des-Neiges
Rue Jean-Brillant, Montréal, QC H3T 1P1
Coordinates: 45.4939, -73.6229

DIZZY CHARACTER CREATOR 0.3.8
=============================

Works with Tekken 3 Expanded (recommended) and with Tekken3Recompiled 0.1.4.

Install
-------
1. Put the "character-builder" folder in the main folder of your game
   (the folder with game.toml). Working in a copy is recommended.
2. Double-click "Start Dizzy Character Creator.cmd". It opens in its own
   window. Keep the black console window open while you use it.

With Tekken 3 Expanded
----------------------
- Step 1 adds a CUSTOM page to the select screen (once).
- Step 2 rebuilds the game (once, and again after game updates).
- Every fighter you save goes on the CUSTOM page with its own portrait and
  name plate. On the select screen, press R2 twice (or L2 once) to get there.
  Saving, deleting or importing a fighter updates the page right away; just
  restart the game. No rebuild needed.
- Up to 12 fighters fit on the CUSTOM page.
- Names use Tekken 3's own name font: there is no F or Q, and 2 is the only
  digit. Very long names do not fit the name plate.
- Custom fighters are not picked as CPU opponents yet.
- The creator never removes a fighter from the CUSTOM page on its own.
  Fighters the game has that are not in this creator's "characters"
  folder (for example from another copy of the creator) are listed under
  "On the Custom page, not in this library": add them to your library
  (their portrait is taken from the game files) or remove them from the
  game after confirming.

With Tekken3Recompiled
----------------------
- Your fighter uses Jun's slot while you play through the creator. Starting
  the game from the normal launcher gives you the normal game with Jun.

Sharing
-------
"Export" creates a .t3char file you can share. Others load it with
"Import package". A package only contains a description and images, never
game files or programs.

Costumes and colours
--------------------
With Tekken 3 Expanded, "3D model" (above the portrait) shows your fighter's
costumes in 3D, read from your own disc the first time (kept in the "cache"
folder). Drag to turn, scroll to zoom, double-click to reset.
On the "Colours" tab (next to "Fighter"), "+ Colour variant" makes a
recoloured copy of a costume. Under "Clothing" every piece of clothing and
accessory is listed (click one, or click it on the model): give it a colour,
or open it to change its colours one by one. "Whole costume" shifts all
colours at once, "Schemes" colours the biggest pieces in one go. Under "In the
game" choose where it goes: it can replace one of the style's costumes, or,
for styles with two costumes, be costume 3 (press Start on the select
screen). Save, Update/Build if the creator asks, then restart the game.

Own 3D models
-------------
With Tekken 3 Expanded, the "3D model" tab gives a fighter its own model:
choose a rigged .fbx (FBX Binary) or .glb file in T-pose or A-pose. Models
without a skeleton are locked. Big models are reduced to PS1 size with a new
texture (1 to 3 minutes). Hair, tails or horns that stick out are folded
down; change that per part before you import. "What makes a model work
well?" on that tab lists the details.

Test
----
"Test" (next to Play) builds the game if needed, starts it, and when you
close the game writes logs	est-report.md: versions, build result, the
Custom page list and the game's Custom/TTT1 log lines. It also appears in
the creator under "Test report", with a Copy button.

Undo
----
Click the Project bar at the top left and choose "Remove the creator's
changes". Rebuild the game afterwards. Your fighters stay in the
"characters" folder.

This is an unofficial fan project. Tekken is a trademark of Bandai Namco.

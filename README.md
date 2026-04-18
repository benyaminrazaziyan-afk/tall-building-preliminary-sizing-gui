Tall Building Preliminary Sizing GUI
A graphical preliminary sizing tool for reinforced-concrete tall buildings.  
This project is intended for concept development and initial member sizing, not for final structural design.
What the program does
The tool provides a conceptual workflow for tall-building preliminary design:
defines a central core wall system
adds distributed perimeter shear walls
keeps corner columns stronger than interior columns
allows square and triangular conceptual plans
estimates structural response using a simplified stiffness-based approach
computes the fundamental period from:
```math
T = 2\\\\pi\\\\sqrt{\\\\frac{M}{K}}
```
produces a graphical plan view on a Tkinter canvas
displays:
core walls
perimeter walls / retaining walls
corner, perimeter, and interior columns
beam and slab preliminary dimensions
key textual outputs such as total weight, stiffness, drift, and period
Main features
Graphical interface built with Tkinter
Plan visualization
Zone-based conceptual sizing
Directional column dimensions for rectangular behavior consistency
Preliminary stiffness decomposition
core stiffness
column stiffness contribution
total stiffness
Preliminary material quantity estimates
Engineering scope
This tool is suitable for:
early-stage concept studies
comparing alternative structural arrangements
generating a first-pass plan layout
preparing an initial model for ETABS / SAP2000 / similar software
This tool is not suitable for:
final design
code compliance checking
nonlinear analysis
performance-based design
foundation design
reinforcement detailing
formal submission documents
Important limitations
The program uses simplified assumptions. Results must be verified with a full structural model.
The following are not included as final design checks:
full 3D structural analysis
response spectrum or time-history analysis
complete wind and seismic code procedures
torsional irregularity verification
P-Delta verification
final shear wall design
final beam/column reinforcement design
diaphragm design
retaining wall design
soil-structure interaction
File structure
```text
tall\\\_building\\\_preliminary\\\_sizing\\\_gui.py
README.md
```
Requirements
Python 3.10+
Standard library only
No external packages are required.

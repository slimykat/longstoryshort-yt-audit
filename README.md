# Long Story Short: YouTube Audit Tool  
A modular auditing system for running and monitoring large-scale recommendation experiments across video formats. Originally built to support the paper: "Long Story Short: Auditing U.S. Political Polarization  in Recommendations for Long- vs. Short-form Videos on YouTube."


## Installation
TBA

## Usage
TBA




## Design Process
This section documents major design decisions as the system evolved from a research prototype into a reusable tool.

### Package Modularization (Feb. 9th)
The initial system was designed for one-off research runs. As experiments scaled, the main challenge became orchestration and visibility: understanding what was running, what failed, and why.

#### Update Plan
- Made batch execution explicit rather than implicit to support reproducibility.
- Modularized task definitions to allow extension to new platforms.
- Added a status tracking layer to reduce reliance on logs.

> *AI Collaboration:*\
> LLMs were used to explore alternative package structures and UI patterns. All architectural decisions and tradeoffs were evaluated and finalized manually.

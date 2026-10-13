**Subject:** Mini-hackathon (Teams, ~1 h): one shared Python toolchain to replace our scattered Excel / Mathcad tools

Hi all,

Ahead of our session, here is what we'll try to crack together.

**The problem (which we've already agreed matters):** our calculation tools are scattered across old projects as Excel sheets, Mathcad files and scripts. They get copied, duplicated and quietly edited, and only their author understands them. We want an AI-assisted toolchain that harvests these tools from wherever they live and passes each one through a central knowledge base. The knowledge base judges whether the tool is worth digesting: is it new, a duplicate, or already covered? What it digests is rebuilt as a standard, documented Python tool that anyone can use and understand. The bonus: reports in Mathcad style, with every formula written out explicitly, so the toolchain fully replaces Excel and Mathcad.

**Building blocks and the questions behind them:**

| Building block / technology to develop | Questions and problems that could arise |
|---|---|
| **Harvesting:** finding the tools | Do we let an agent crawl every project folder (SharePoint, Teams, drives), or select tools carefully? How do we pick the "good" version out of 20 copies? What about client confidentiality and access rights? |
| **Digesting:** Excel / Mathcad into a machine-readable form | Which tool reads them reliably? What about legacy .xmcd/.mcd files, macros, lookups, hidden sheets, or sheets that are mostly screenshots? |
| **The "blender":** AI conversion into Python | How reliable is it? How do we prove a one-to-one match with the original? Who is accountable when a converted tool is wrong? |
| **Central knowledge base:** digest, merge or reject | What is the reference: Eurocodes + national annexes, our own standards, open libraries? How do we decide two tools are "the same"? Who owns the library? |
| **Auditing:** which tool checks the result | Automated unit and dimension checks, an AI reviewer, a human checker, or all three? What evidence is enough to mark a tool "approved"? |
| **Reporting:** Python into human-readable calc reports | Can it be Mathcad-quality (explicit formulas, our title block, clause references) and good enough for checkers and clients? Can non-coders change inputs? |
| **Hosting and use** | Where does it live (GitLab, internal package, web app, Excel add-in)? How do people run it without coding? How are revisions handled? |
| **Adoption and governance** | Who maintains it? Sign-off process, licences (Mathcad, AI tools), data policy, training? |

**What we want to achieve in the session (goals, not a timetable):**
1. Confirm the problem statement and scope quickly; we're already aligned on the why.
2. Walk the chain block by block: what exists today, which tools or approaches could work, and what the biggest risk is.
3. Pick the two or three blockers that would kill the idea if left unsolved.
4. Leave with brainstormed ideas, MVPs, working solutions or concrete proposals for how to solve or develop each block, plus an owner for the next step.

**Please bring** one real Excel or Mathcad tool from a past project that you'd love to see converted, along with anything you've already tried. I've built a rough prototype of the chain; we can use it as something to poke holes in, not as the answer.

See you there,
[Name]

# Quantum & AGI for Informal Workers: Honest Technical Assessment

**Prepared for:** Valentine Owuor  
**Date:** 2026-07-24  
**Verdict First:** Most problems described do NOT require quantum computing. Classical AI/ML handles most of them adequately. Quantum advantage exists in a narrow band of problems, and even there, practical timelines are 5-15 years. AGI is mostly overkill where narrow AI suffices. Here's the honest breakdown.

---

## PART 1: Problems Classical Computers CAN'T Solve (Honest Assessment)

### 1A. Combinatorial Optimization Problems

#### Problem: Optimal Pricing Across 1000+ Products, 100+ Vendors

**Is this classically intractable?** NO — mostly not.

- A mama mboga with 50 products and daily pricing decisions is a **small** optimization problem. Classical methods (linear programming, gradient-based optimization, even simple heuristics) handle this trivially. A smartphone app could do it.
- Even 1,000 products × 100 vendors = 100,000 variables. Modern solvers (Gurobi, CPLEX) handle millions of variables in seconds for linear/quadratic programs.
- The complexity only becomes NP-hard if you add hard constraints like integer variables (must buy whole crates), time-coupled decisions (today's price affects tomorrow's demand), and game-theoretic competition (each vendor reacts to others). This becomes a **Stackelberg game** or **multi-agent RL problem** — hard but not quantum-hard.

**Does quantum help?** Marginally, maybe. QAOA (Quantum Approximate Optimization Algorithm) has been benchmarked extensively against classical methods as of 2024-2026. The verdict from the research community: **QAOA does NOT currently outperform classical heuristics** (like simulated annealing, tabu search, or even greedy algorithms) for most combinatorial optimization problems at practical scales. The Nature paper on Quantum Optimization Benchmarking Library (2026) confirms this gap remains open.

**Honest verdict:** Classical AI handles this. A well-trained ML model on historical transaction data could optimize a mama mboga's pricing better than she does manually. No quantum needed.

---

#### Problem: Optimal Inventory Ordering for Mama Mboga (50 products)

**Is this NP-hard?** Not in practice.

This is essentially a **multi-product newsvendor problem** with perishability. With 50 products, spoilage rates, and supplier costs, this is a medium-sized stochastic optimization problem. Classical methods (stochastic programming, reinforcement learning, even simple statistical forecasting) solve this well.

- Real-world retailers like Walmart and Amazon manage millions of SKUs with classical optimization.
- The informal sector version is simpler (fewer products, fewer suppliers, shorter planning horizons).

**Does quantum help?** No. This problem is too small for quantum advantage to matter.

**Honest verdict:** Classical ML/optimization solves this completely. An app on a feature phone could do it.

---

#### Problem: Optimal Loan Portfolio Allocation Across 1M+ Micro-Loans

**Is this classically intractable?** It's getting closer to hard territory.

- Portfolio optimization with 1M+ assets and **correlated default risks** is a large-scale convex optimization problem if you use simplified models (mean-variance, CVaR). Classical solvers handle this.
- BUT: If you model **tail dependencies** (what happens when defaults cluster — e.g., during a drought that hits all farmers in a region), you need to simulate correlated default scenarios. This is where Monte Carlo simulation with thousands of correlated variables becomes expensive.
- The dimensionality: 1M loans × ~20 risk factors = 20M-dimensional correlation matrix. Classical methods struggle with this in real-time.

**Does quantum help?** Possibly yes, eventually.

- **Quantum Monte Carlo** offers a provable **quadratic speedup** (Montanaro 2015): if classical Monte Carlo needs N samples, quantum needs O(√N). For tail-risk estimation requiring 10⁶ classical samples, quantum needs ~10³. This is real.
- However, this requires **fault-tolerant quantum computers** that don't exist yet. Current NISQ devices can't run quantum Monte Carlo at useful scales.
- Timeline: 2030-2035 for practical quantum Monte Carlo on financial problems (IBM, JPMorgan estimates).

**Honest verdict:** Classical computers handle this today with some engineering effort. Quantum offers a genuine speedup (quadratic) but only becomes necessary if you need real-time risk updates across millions of loans. Timeline: 7-10 years.

---

### 1B. Pattern Recognition Problems

#### Problem: Real-Time Fraud Detection in M-Pesa (Millions of Transactions)

**Is this beyond classical?** NO.

- This is a solved problem classically. Banks and fintech companies already do real-time fraud detection on millions of transactions using classical ML (gradient boosting, neural networks, graph neural networks).
- M-Pesa processes ~30M transactions/day. Modern classical systems handle this easily with stream processing (Kafka, Flink) + ML models.
- The NQCC (UK National Quantum Computing Centre) 2025 report mentions quantum ML for fraud detection as a research interest, not a necessity.

**Does quantum help?** Not meaningfully. Classical deep learning is already very good at this.

**Honest verdict:** Classical AI solves this today. No quantum advantage demonstrated or needed.

---

#### Problem: Predicting Market Crashes/Price Spikes in Informal Markets

**Is this classically predictable?** Partially — and quantum doesn't help much.

- Price spikes in informal markets (e.g., tomato prices in Nairobi) are driven by supply shocks (weather, transport disruption, hoarding). These are **chaotic systems** with high sensitivity to initial conditions.
- Classical time-series models (ARIMA, Prophet, LSTM networks) can predict short-term price movements with moderate accuracy. Quantum doesn't fundamentally change this.
- The hard problem is **early warning** — detecting precursor signals in noisy data. This is a pattern recognition problem where more data + better classical ML usually beats quantum approaches.

**Does quantum help?** Not for this specific problem. Quantum computing doesn't offer advantage for time-series prediction.

**Honest verdict:** Classical ML with good data solves this. The bottleneck is data quality and availability, not computation.

---

#### Problem: Identifying Coordination Failures (Everyone Oversupplying Tomatoes)

**Can classical systems see this?** YES, with proper data infrastructure.

- This is a **game theory / mechanism design** problem. Detecting herding behavior in supply chains is well-studied in economics (cobweb models).
- Classical graph analytics and agent-based models can identify coordination failures from transaction data.
- The challenge is data collection (informal transactions aren't digitized), not computation.

**Does quantum help?** No. This is a data problem, not a computation problem.

**Honest verdict:** Classical systems solve this if you have the data. The real problem is digitizing informal transactions.

---

### 1C. Simulation Problems

#### Problem: Simulating Policy Impact on Millions of Informal Workers

**Can classical computers do this?** Yes, with agent-based modeling.

- Agent-based models (ABMs) with millions of agents are computationally expensive but feasible on modern clusters. Projects like Sugarscape and economic ABMs routinely simulate 10⁶-10⁷ agents.
- The challenge is **calibration** (making the model match reality), not raw computation.
- Quantum computing offers no known advantage for agent-based simulation.

**Does quantum help?** No. ABMs are inherently sequential (each agent's decision affects others) and don't map well to quantum circuits.

**Honest verdict:** Classical HPC (high-performance computing) handles this. The bottleneck is model design and data, not compute.

---

#### Problem: Monte Carlo Simulation for Credit Risk (Thousands of Correlated Variables)

**Is quantum actually faster here?** YES, in theory.

- Quantum amplitude estimation provides a **quadratic speedup** over classical Monte Carlo (proven, not theoretical).
- For risk models requiring 10⁶ scenarios, quantum reduces this to ~10³ circuit evaluations.
- This is one of the **most credible** quantum advantage claims in finance.
- JPMorgan, Goldman Sachs, and others are actively developing quantum Monte Carlo for this exact use case.

**BUT:** Requires fault-tolerant quantum computers. Current NISQ devices cannot run this. Timeline: 2030-2035 for practical use.

**Honest verdict:** Genuine quantum advantage (quadratic speedup). But 7-10 years away from practical deployment. Classical methods work fine today.

---

#### Problem: Modeling the Informal Economy as a Complex Adaptive System

**Is this classically feasible?** Partially.

- Complex adaptive systems (CAS) with millions of heterogeneous agents, emergent behavior, and feedback loops are genuinely hard to simulate.
- Classical ABMs can handle 10⁶ agents but struggle with **real-time** simulation and **scenario exploration** (testing thousands of policy alternatives).
- Quantum simulation (using quantum computers to simulate quantum systems) doesn't apply here — the informal economy isn't a quantum system.

**Does quantum help?** Not directly. Quantum computing is good at simulating quantum physics, not economic systems.

**Honest verdict:** Classical HPC handles this for offline analysis. Real-time simulation of millions of agents remains hard for both classical and quantum.

---

## PART 2: Problems Humans CAN'T Solve (Honest Assessment)

### 2A. Real-Time Decision Making

#### Problem: Mama Mboga Optimizing 50 Prices, 50 Times/Day

**Can a human optimize this?** No — and classical AI already solves it.

- This is a **solved problem** for classical AI. Reinforcement learning or simple statistical models can optimize pricing in real-time.
- The human bottleneck is cognitive load: tracking 50 products × 50 price changes × competitor prices × demand patterns = 125,000 data points/day. No human can optimize this.
- A classical smartphone app with a simple ML model could do this today.

**Does AGI help?** No — narrow AI suffices. You don't need general intelligence to optimize prices.

**Honest verdict:** Classical narrow AI solves this completely. No AGI or quantum needed.

---

#### Problem: Detecting Supply Shortages for 10,000 Workers from Transaction Patterns

**Can a human see this coming?** No. Can classical AI? YES.

- This is an **anomaly detection + time-series forecasting** problem. Classical ML (isolation forests, autoencoders, LSTM networks) excels at this.
- M-Pesa and similar platforms already use classical ML for fraud detection — the same techniques apply to supply chain disruption detection.
- The challenge is data integration (connecting transaction data with weather, transport, market data), not computation.

**Does AGI help?** Not for this specific task. Narrow AI with good data pipelines solves it.

**Honest verdict:** Classical AI solves this. The bottleneck is data integration and infrastructure, not intelligence.

---

#### Problem: Real-Time Credit Scoring Based on Every Transaction

**Can a human track this?** No. Can classical AI? YES, and it already does.

- Companies like Tala, Branch, and M-Shwari already use classical ML for real-time credit scoring based on mobile money transactions.
- This is a **classification problem** (creditworthy or not) with structured data. Classical gradient boosting (XGBoost, LightGBM) is state-of-the-art.
- No quantum or AGI advantage.

**Honest verdict:** Solved problem. Classical ML handles this perfectly.

---

### 2B. Cross-Market Intelligence

#### Problem: Tomato Prices in Migori Affecting Nairobi 3 Days Later

**Can a human see this pattern?** Unlikely — but classical AI can.

- This is a **spatial-temporal forecasting** problem. Classical methods (VAR models, graph neural networks on supply chain networks) can detect cross-market price transmission.
- Econometrics has studied price transmission for decades (the law of one price, cointegration analysis). Classical methods work well.
- The challenge is having price data from Migori in the first place (data collection, not computation).

**Does AGI help?** Not for this. Narrow AI with spatial-temporal models solves it.

**Honest verdict:** Classical econometrics + ML solves this. The bottleneck is data collection from informal markets.

---

#### Problem: Connecting a Boda-Boda Rider in Kisumu with a Mama Mboga in Nakuru

**Can a human connect these dots?** No — but this is a **graph analytics** problem, not an AGI problem.

- If you have transaction data, classical graph databases (Neo4j) and community detection algorithms can find hidden supply chain connections.
- This is standard network analysis — no quantum or AGI advantage.

**Honest verdict:** Classical graph analytics solves this. Data infrastructure is the bottleneck.

---

#### Problem: Predicting Drought Impact Across 5 Regions in 2 Weeks

**Can a human model this?** No. Can classical AI? YES.

- This is a **spatial-temporal causal inference** problem. Classical methods (Granger causality, structural equation models, causal ML) can model how drought in one region propagates to others.
- Climate-agriculture models (like those used by FEWS NET) already do this classically.

**Honest verdict:** Classical models solve this. The challenge is data quality and model calibration, not computation.

---

### 2C. Scale Coordination

#### Problem: Coordinating 100,000 Workers' Savings for Collective Investment

**Can humans organize this without technology?** Barely — but classical technology handles it.

- This is a **mechanism design + matching** problem. Classical platforms (like M-Changa, GoFundMe) coordinate collective action at scale.
- The optimization component (optimal allocation of pooled funds) is a standard portfolio optimization problem — classical solvers handle it.
- Blockchain/smart contracts could automate trust and governance.

**Does quantum/AGI help?** No. Classical platforms + smart contracts solve this.

**Honest verdict:** Classical technology solves this. The challenge is trust, governance, and regulation, not computation.

---

#### Problem: Matching 50,000 Buyers with 50,000 Sellers in Real-Time

**Can humans do this?** No. Can classical systems? YES — this is Uber/Airbnb's business model.

- Real-time matching at scale is a **solved problem**. Uber matches millions of riders with drivers in seconds using classical algorithms.
- The optimization (minimizing total distance/wait time) is a large assignment problem — classical algorithms (Hungarian algorithm, auction-based methods) handle it.

**Honest verdict:** Solved problem. Classical systems do this at much larger scales already.

---

#### Problem: Detecting Exploitation of 1,000 Workers by the Same Supplier

**Can humans see this?** No. Can classical AI? YES.

- This is a **fraud/pattern detection** problem. Classical graph analytics and clustering can identify suppliers with anomalous patterns across workers.
- Similar to anti-money laundering (AML) detection — classical ML already solves this at scale in banking.

**Honest verdict:** Classical ML solves this. Data infrastructure is the bottleneck.

---

## PART 3: Honest Summary Assessment

### What Quantum Computing ACTUALLY Offers

| Problem | Quantum Advantage? | Timeline | Honest Assessment |
|---------|-------------------|----------|-------------------|
| Optimal pricing (50 products) | ❌ No | N/A | Too small. Classical solves it. |
| Inventory optimization | ❌ No | N/A | Too small. Classical solves it. |
| Portfolio allocation (1M loans) | ✅ Quadratic speedup | 2030-2035 | Real but needs fault-tolerant QC. |
| Fraud detection (M-Pesa) | ❌ No | N/A | Classical ML already solves it. |
| Market crash prediction | ❌ No | N/A | Data problem, not compute problem. |
| Coordination failure detection | ❌ No | N/A | Classical graph analytics works. |
| Policy simulation (millions of workers) | ❌ No | N/A | Classical ABM handles it. |
| Monte Carlo for credit risk | ✅ Quadratic speedup | 2030-2035 | Most credible quantum advantage claim. |
| Complex adaptive systems modeling | ❌ No | N/A | Not a quantum problem. |
| Real-time matching (buyers/sellers) | ❌ No | N/A | Classical algorithms solve it. |

### What AGI ACTUALLY Offers

| Problem | AGI Needed? | Honest Assessment |
|---------|------------|-------------------|
| Price optimization | ❌ No | Narrow RL solves it. |
| Supply shortage detection | ❌ No | Narrow anomaly detection works. |
| Credit scoring | ❌ No | Narrow ML (XGBoost) is SOTA. |
| Cross-market intelligence | ❌ No | Classical econometrics + ML works. |
| Supply chain discovery | ❌ No | Graph analytics solves it. |
| Drought impact prediction | ❌ No | Classical causal models work. |
| Collective investment coordination | ❌ No | Classical platforms + smart contracts. |
| Exploitation detection | ❌ No | Classical fraud detection works. |

### The TRUTH: Where Does This Leave Us?

**For 95% of problems informal workers face:**
- Classical AI/ML solves them TODAY or will solve them in 1-3 years.
- The bottleneck is **data infrastructure** (digitizing informal transactions), **connectivity** (internet access), and **trust** (adoption) — not computation.
- A well-designed app using classical ML on a smartphone could transform a mama mboga's business today.

**Where quantum computing offers genuine advantage (the ~5%):**
1. **Monte Carlo simulation for credit risk** — quadratic speedup, but needs fault-tolerant QC (2030-2035)
2. **Large-scale portfolio optimization** with correlated risks — marginal advantage, same timeline
3. **Molecular simulation** for agricultural inputs (fertilizer, pesticides) — genuine quantum advantage, but this benefits the supply chain, not directly the informal worker

**Where AGI offers genuine advantage:**
- Honestly? Very little for informal workers. AGI's advantage is in **open-ended reasoning** and **transfer learning across domains** — useful for research and policy design, not for the operational problems informal workers face daily.
- The one area where AGI might help: **natural language interfaces** in local languages, enabling workers who can't read/write to interact with complex systems. But this is more about language models (which already exist) than AGI.

### The REAL Barriers (Not Computation)

1. **Data**: Informal economy transactions are mostly cash/offline. No data = no AI.
2. **Connectivity**: Many informal workers lack reliable internet. Cloud-based solutions don't work.
3. **Trust**: Workers don't trust apps with their money. Human intermediaries (chamas, SACCOs) matter.
4. **Cost**: Quantum computers cost millions. Informal workers earn $2-10/day. The economics don't work.
5. **Literacy**: Many informal workers can't use complex apps. UX design matters more than algorithm sophistication.

### Recommendations for Valentine Owuor

1. **Don't wait for quantum or AGI.** Classical AI on smartphones can transform informal workers' lives TODAY.
2. **Focus on data infrastructure first.** Digitize transactions, build data pipelines. This unlocks everything.
3. **Build for the existing tech stack.** Feature phones, SMS, USSD — not quantum computers.
4. **Use classical ML for pricing, inventory, credit scoring.** It's proven, cheap, and effective.
5. **Watch quantum Monte Carlo for credit risk** — it's the one genuine quantum advantage that could matter in 7-10 years.
6. **Don't overclaim.** The problems informal workers face are mostly about access, trust, and infrastructure — not about computational complexity.

---

## Sources

- Eisert & Preskill, "Mind the gaps: The fraught road to quantum advantage" (arXiv:2510.19928, 2025) — Honest assessment of quantum computing gaps
- Q-CTRL, "Practical quantum advantage signals a new commercial era" (May 2026) — 3,000× speedup in materials simulation, NOT in optimization
- Nature, "The Quantum Optimization Benchmarking Library" (2026) — QAOA vs classical benchmarks
- IBM Quantum Roadmap (2025) — Fault-tolerant QC timeline: 2029-2033
- Montanaro, "Quantum speedup of Monte Carlo methods" (2015) — Proven quadratic speedup
- NQCC Quantum Computing Use Case Compendium (2025) — Practical quantum applications assessment
- Springer, "Benchmarking variational quantum algorithms for combinatorial optimization" (2026) — VQA still behind classical
- IBM Quantum Readiness Index (2025) — Quantum advantage expected by late 2026 in specific domains

---

*This report prioritizes honesty over hype. If a classical computer can solve it, we said so. If quantum is only marginally better, we said so. Valentine deserves the truth.*

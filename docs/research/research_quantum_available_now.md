# Quantum Computing: What's Available RIGHT NOW (July 2026)

**Research Date:** July 24, 2026
**Prepared For:** Valentine Owuor — Msaidizi/Angavu Intelligence
**Purpose:** Actionable inventory of quantum tools, services, and frameworks available TODAY

---

## PART 1: What's Available RIGHT NOW — By Player

### 1. IBM Quantum

**The most accessible quantum platform on Earth. Free tier confirmed.**

#### IBM Quantum Network — Free Access
- **IBM Quantum Open Plan** — FREE, no credit card required
  - 10 minutes of quantum runtime every 28 days on real quantum hardware
  - Anyone with an internet connection can sign up at quantum.cloud.ibm.com
  - Special one-time promotion (March 2026): Use 20 minutes within 12 months → unlock **180 minutes** for the next 12 months
  - Access to **Heron r2 (ibm_kingston)** — one of IBM's highest-performing systems — now available to ALL Open Plan users (previously paid-only)

#### Qiskit Runtime — Algorithms Available NOW
- **Qiskit** — open-source Python SDK, largest quantum community (5,857+ papers citing IBM Quantum/Qiskit)
- **Qiskit Runtime** — cloud-based execution with primitives (Estimator, Sampler)
- **Qiskit v2.4** (2026) — improved C-API, faster fault-tolerant compilation
- **Qiskit Fermions** — new quantum chemistry library for fermionic systems
- **Qiskit Functions** — including **Quantum Portfolio Optimizer** (directly relevant to fintech!)
- Available algorithms: VQE, QAOA, quantum Monte Carlo, Grover's search, portfolio optimization

#### IBM Quantum Hardware — What Can It Do?
- **Heron r3** — latest processor, low error rates for complex hybrid workflows
- **Nighthawk** — square-lattice connectivity for 2D simulations
- **ibm_boston** — best error per gate level (EPLG) at 0.19%
- **Total fleet:** 16 QPUs, 2,344 total qubits, 330K+ CLOPS
- **340K circuit layer operations per second** on Heron r2
- Median two-qubit error rate: 2.03×10⁻³

#### IBM Quantum Serverless
- Hybrid quantum-classical workflows where classical compute and quantum compute are orchestrated automatically
- You write a single program; the system decides what runs on QPU vs CPU/GPU
- Available through Qiskit Runtime

#### What Problems Can You Solve TODAY with IBM?
- Portfolio optimization (built-in Qiskit Function!)
- Quantum machine learning (classification, clustering)
- Combinatorial optimization (routing, scheduling)
- Quantum chemistry simulations
- Financial Monte Carlo simulations
- **Best for:** Learning, prototyping, small-to-medium optimization problems

---

### 2. Google Quantum AI

#### Cirq Framework — Available NOW
- **Cirq** — open-source Python library, free, `pip install cirq`
- Write, manipulate, optimize quantum circuits
- Built-in simulators (wave function, density matrix)
- **qsim** — state-of-the-art wave function simulator
- **Quantum Virtual Machine (QVM)** — simulate Google's quantum hardware with realistic noise models
- Textbook algorithms: QAOA, VQE, Grover's, quantum walks, quantum teleportation
- TensorFlow Quantum integration for hybrid quantum-classical ML

#### Google Quantum AI Cloud Access
- **Quantum Engine API** — access to Google's quantum processors
- **NOTE:** As of March 2026, the Quantum Engine API is "not yet open for public access" — requires Google Cloud project and may be limited to research partners
- Google expanded beyond superconducting processors in March 2026 (new qubit modalities)

#### Willow Chip
- Google's latest quantum processor
- Demonstrated quantum error correction milestones
- **Not directly accessible** to the general public — research/partnership access only
- Best used indirectly through Cirq simulation

#### What You Can Do TODAY with Google Quantum AI
- Full quantum circuit simulation locally (free, unlimited)
- QVM realistic hardware simulation
- Algorithm prototyping and testing
- **Limitation:** Real hardware access is restricted
- **Best for:** Algorithm development, simulation, ML integration

---

### 3. NVIDIA CUDA-Q

#### What Is CUDA-Q?
- NVIDIA's open-source platform for **hybrid quantum-classical computing**
- Formerly cuQuantum, now CUDA-Q
- `pip install cudaq` — free, open-source
- **Write once, run everywhere** — QPU agnostic, integrates with 75% of publicly available QPUs
- Supports Python and C++ programming models

#### GPU-Accelerated Quantum Simulation
- **YES — you can simulate quantum computing on GPUs without quantum hardware**
- Massive speedups: Alice & Bob achieved 9.25x speedup in quantum error correction decoding using GPU-accelerated simulation
- Simulate quantum circuits on NVIDIA GPUs (DGX, cloud GPU instances)
- Enables "quantum-accelerated supercomputing" — GPU + QPU in a single program

#### DGX Quantum
- NVIDIA's system for connecting GPUs directly to quantum processors
- GPU-QPU integration in real-time
- Partners: PsiQuantum, Classiq, Qilimanjaro, Alice & Bob, and more

#### NVIDIA Quantum Ecosystem Partners (2026)
- PsiQuantum — photonic quantum computing
- Classiq — high-level quantum application modeling
- Qilimanjaro — integrated CUDA-Q into QiliSDK
- Alice & Bob — error correction acceleration
- 75% of publicly available QPUs supported

#### What You Can Do TODAY with NVIDIA
- Simulate quantum algorithms on your own GPU hardware
- Build hybrid quantum-classical applications
- Develop and test quantum error correction
- Use with cloud GPU instances (AWS, GCP, Azure)
- **Best for:** Researchers, HPC environments, quantum simulation at scale

---

### 4. Amazon Braket

#### Hardware Available NOW
| Provider | QPU | Per-Task | Per-Shot |
|----------|-----|----------|----------|
| AQT | IBEX-Q1 | $0.30 | $0.0235 |
| IonQ | Forte | $0.30 | $0.08 |
| IQM | Emerald | $0.30 | $0.0016 |
| IQM | Garnet | $0.30 | $0.00145 |
| QuEra | Aquila | $0.30 | $0.01 |
| Rigetti | Cepheus | $0.30 | $0.000425 |

#### Reservation Pricing (Dedicated Access)
- AQT IBEX-Q1: $4,800/hour
- IonQ Forte: $7,000/hour
- IQM Emerald: $4,000/hour
- QuEra Aquila: $2,500/hour
- Rigetti Cepheus: $4,100/hour

#### Free Tier / Simulators
- **Local simulator** — FREE, included in Amazon Braket SDK
- **SV1** (State Vector) — general-purpose simulator, pay per use
- **DM1** (Density Matrix) — noise simulation
- **TN1** (Tensor Network) — for larger circuits
- AWS Free Tier includes some SV1 simulator usage

#### Hybrid Quantum-Classical Jobs
- Fully managed execution of hybrid algorithms
- Jupyter notebook environments included
- Pay only for what you use (no upfront charges)

#### What You Can Run TODAY
- QAOA, VQE, quantum annealing (QuEra), gate-based circuits
- Portfolio optimization, combinatorial optimization
- Quantum machine learning experiments
- **Best for:** Multi-hardware comparison, production-grade hybrid workflows

---

### 5. Microsoft Azure Quantum

#### Hardware Providers Available
- **IonQ** — trapped ion (Aria 1: 25 qubit, Forte: 36 qubit)
- **Quantinuum** — trapped ion (world's most powerful quantum computer)
- **Pasqal** — neutral atom
- **Rigetti** — superconducting

#### Pricing (IonQ on Azure)
- Token-based pricing: AQT = m + 0.000220 × (N₁q × C) + 0.000975 × (N₂q × C)
- Minimum per execution: $12.42 (no error mitigation) or $97.50 (with error mitigation)
- Pay-as-you-go and monthly subscription plans available

#### Q# Language
- Microsoft's quantum programming language
- Integrated with Azure Quantum
- Can write quantum programs, compile, and run on multiple hardware backends
- Rich library of quantum operations and simulators

#### Azure Quantum Credits
- **30-day free trial** with Azure Quantum credits available
- Credits can be used across multiple providers (IonQ, Quantinuum, etc.)
- New Azure accounts get $200 credit for Azure services

#### What You Can Do
- Run on multiple quantum hardware providers from one interface
- Use Q# or Python
- Hybrid quantum-classical workflows
- **Best for:** Enterprise integration, multi-provider access, Microsoft ecosystem users

---

### 6. Other Players

#### D-Wave — Quantum Annealing (MOST PRACTICAL FOR OPTIMIZATION)
- **Leap™ Quantum Cloud Service** — cloud access to real quantum annealers
- **Ocean™ SDK** — open-source Python tools, `pip install dwave-ocean-sdk`
- **Use cases available NOW:**
  - Workforce scheduling
  - Production scheduling
  - Logistics routing
  - Resource optimization
  - Cargo loading
  - Price optimization (published research: quantum annealing for price optimization under cross-elastic demand)
- **D-Wave Launch™** — professional services program to on-board businesses
- Free tier available (limited minutes on Leap cloud)
- **THE MOST PRACTICAL quantum platform for business optimization TODAY**

#### Xanadu — Photonic Quantum Computing
- **PennyLane** — open-source Python framework for quantum ML
- `pip install pennylane`
- Integrates with TensorFlow, PyTorch, JAX
- Cloud access to Xanadu's photonic quantum processors
- **Borealis** — photonic quantum computer, accessible via cloud
- Best for: Quantum machine learning, differentiable quantum circuits

#### Rigetti
- **Quantum Cloud Services (QCS)** — cloud access to superconducting QPUs
- Available through Amazon Braket
- **Cepheus** processor available on Braket

#### IonQ
- Trapped ion quantum computing
- Available through Amazon Braket, Azure Quantum, Google Cloud
- **Forte** and **Aria** systems
- Highest fidelity gates among cloud-accessible systems
- Available NOW on multiple cloud platforms

#### African Quantum Initiatives
- **Wits University (South Africa)** — Fintech Hub with quantum computing research focus
- **3rd Wits Global Fintech Conference 2026** — includes "High-Performance Computing, Quantum Computing, & Cryptography" track
- **Qilimanjaro** (Spain-based, African roots) — integrated NVIDIA CUDA-Q into their SDK
- **No major African quantum hardware** — but African researchers are accessing cloud quantum platforms
- **Opportunity:** Msaidizi/Angavu could be among the first African fintech companies to actively use quantum computing

---

## PART 2: What Problems Can Be Solved TODAY

### 2.1 Problem Types by Platform

| Problem Type | Best Platform | Quantum Advantage | Cost to Start |
|-------------|---------------|-------------------|---------------|
| **Portfolio Optimization** | IBM Qiskit (built-in!), D-Wave | Moderate (QAOA for small portfolios) | FREE (IBM Open Plan) |
| **Route Optimization** | D-Wave, Amazon Braket | High for combinatorial problems | FREE (D-Wave Leap) |
| **Workforce Scheduling** | D-Wave | High (quantum annealing excels) | FREE (D-Wave Leap) |
| **Fraud Detection (ML)** | PennyLane + classical GPU | Experimental (quantum kernels) | FREE (PennyLane) |
| **Credit Risk Modeling** | IBM Qiskit, Azure Quantum | Moderate (Monte Carlo) | FREE (IBM) |
| **Supply Chain Optimization** | D-Wave, Amazon Braket | High for complex logistics | FREE (D-Wave) |
| **Pricing Optimization** | D-Wave | High (published research) | FREE (D-Wave Leap) |
| **Quantum Monte Carlo** | IBM, Azure | Quadratic speedup potential | FREE (IBM) |

### 2.2 Quantum Advantage vs Classical — Honest Assessment (July 2026)

**Where quantum HAS advantage TODAY:**
- **Combinatorial optimization** (50-1000+ variables) — D-Wave annealing
- **Quantum simulation** of molecular/chemical systems
- **Specific sampling problems** where quantum randomness helps

**Where quantum MIGHT help (experimental):**
- **Portfolio optimization** — promising for large portfolios with many constraints
- **Quantum ML kernels** — potential advantage for specific classification tasks
- **Monte Carlo methods** — quadratic speedup in theory, limited by current hardware

**Where classical is STILL better:**
- Small optimization problems (<50 variables)
- Standard ML tasks with sufficient data
- Real-time decisioning (quantum has latency)
- Most day-to-day fintech operations

### 2.3 Cost Summary

| Platform | Free Tier | Paid Starting Cost |
|----------|-----------|-------------------|
| IBM Quantum | 10 min/28 days (180 min with promo) | Paid plans for more runtime |
| Google Cirq | Unlimited simulation (local) | Hardware access: research partnerships |
| NVIDIA CUDA-Q | Free, open-source | GPU cloud costs (AWS/GCP) |
| Amazon Braket | Local simulator free, some SV1 free | $0.30/task + per-shot fees |
| Azure Quantum | 30-day trial credits | $12.42+ per execution (IonQ) |
| D-Wave Leap | Free tier with limited minutes | Pay-as-you-go |
| PennyLane | Free, open-source | Hardware access varies |

### 2.4 Minimum Viable Use Case for African Fintech

**RECOMMENDED: D-Wave + IBM Quantum**

**Use Case: Agent Network Optimization**
- Problem: Optimizing placement and cash allocation of mobile money agents across Kenya/East Africa
- Variables: Agent locations, cash demand patterns, travel distances, rebalancing schedules
- Why quantum: Classic combinatorial optimization that scales exponentially
- D-Wave's quantum annealing is PURPOSE-BUILT for this exact problem type
- Cost: FREE (D-Wave Leap free tier + IBM Open Plan)
- Skills needed: Python developer with optimization background (no quantum physicist needed)

**Use Case: Credit Scoring Enhancement**
- Problem: Quantum-enhanced feature selection for credit scoring of informal economy workers
- Approach: Use quantum approximate optimization (QAOA) on IBM to select optimal feature subsets
- Cost: FREE
- Skills needed: Data scientist + basic Qiskit knowledge

### 2.5 Can You Use It Without a Quantum Physicist?

**YES — for these platforms:**
- **IBM Qiskit** — Extensive tutorials, courses, community. Qiskit Functions hide quantum complexity.
- **D-Wave Ocean SDK** — Business-oriented examples. D-Wave Launch program helps on-board.
- **Amazon Braket** — Managed notebooks, examples for common use cases
- **PennyLane** — Looks like PyTorch, familiar to ML engineers
- **NVIDIA CUDA-Q** — If your team knows CUDA/Python, they can learn it

**NO — you need quantum expertise for:**
- Designing novel quantum algorithms
- Interpreting quantum error rates and optimizing circuits
- Azure Quantum with Q# (steeper learning curve)
- Custom quantum error correction

---

## PART 3: Msaidizi/Angavu Quantum Roadmap

### 3.1 Where to Start (Cheapest → Most Impactful)

**IMMEDIATE (This Week) — $0:**
1. ✅ Sign up for **IBM Quantum Open Plan** (free) at quantum.cloud.ibm.com
2. ✅ Install **Qiskit** (`pip install qiskit`) and run tutorials
3. ✅ Install **D-Wave Ocean SDK** (`pip install dwave-ocean-sdk`) and try optimization examples
4. ✅ Install **Cirq** (`pip install cirq`) for local quantum simulation
5. ✅ Install **PennyLane** (`pip install pennylane`) for quantum ML experiments

**WEEK 2-4 — $0:**
6. Run IBM's **"Designing and Leading Quantum Projects"** course (free)
7. Run IBM's **"Integrating quantum and HPC"** course (free)
8. Try the **Qiskit Quantum Portfolio Optimizer** Function on real hardware
9. Build a D-Wave solution for agent network optimization (use their code samples)
10. Benchmark quantum vs classical on a real Msaidizi problem

**MONTH 2-3 — <$100:**
11. Run experiments on Amazon Braket (IonQ Forte, Rigetti Cepheus) for multi-hardware comparison
12. Explore NVIDIA CUDA-Q simulation on cloud GPUs
13. Build a proof-of-concept quantum-enhanced credit scoring model
14. Document results and publish findings

### 3.2 Minimum Investment to Start Experimenting

| Item | Cost | Notes |
|------|------|-------|
| IBM Quantum Open Plan | $0 | Free real quantum hardware access |
| D-Wave Leap Free Tier | $0 | Free quantum annealing access |
| Qiskit/Ocean/Cirq/PennyLane | $0 | All open-source |
| Amazon Braket experiments | ~$50-100 | For testing multiple QPUs |
| Cloud GPU (NVIDIA simulation) | ~$50-100 | For GPU-accelerated simulation |
| Learning (IBM courses) | $0 | Free courses available |
| **TOTAL MINIMUM** | **$0** | Can start completely free |
| **TOTAL WITH HARDWARE TESTING** | **$100-200** | For serious experimentation |

### 3.3 Skills the Team Needs

**Immediate (learn in 2-4 weeks):**
- Python programming (assuming team already has this)
- Basic linear algebra and probability (refresher)
- Qiskit fundamentals (IBM has free courses)
- Combinatorial optimization concepts (for D-Wave)

**Medium-term (1-3 months):**
- Quantum circuit design and optimization
- QAOA and VQE algorithm implementation
- D-Wave problem formulation (QUBO/Ising models)
- Quantum machine learning basics (PennyLane)

**Long-term (3-6 months):**
- Quantum error mitigation techniques
- Hybrid quantum-classical algorithm design
- Quantum advantage benchmarking methodology
- Post-quantum cryptography awareness (for security)

### 3.4 Six-Month Quantum Roadmap

```
MONTH 1: Foundation
├── Sign up for all free platforms (IBM, D-Wave, PennyLane)
├── Complete IBM quantum learning courses
├── Build team quantum literacy (2-3 developers)
├── Identify 3 candidate problems from Msaidizi operations
└── Run first quantum circuit on real hardware

MONTH 2: Exploration
├── Implement first optimization problem on D-Wave
├── Test Qiskit Portfolio Optimizer on real data
├── Benchmark quantum vs classical performance
├── Explore Amazon Braket multi-hardware comparison
└── Join IBM Quantum Network community

MONTH 3: Proof of Concept
├── Build working prototype: quantum-optimized agent allocation
├── Test quantum credit scoring model
├── Document performance metrics and limitations
├── Evaluate NVIDIA CUDA-Q for simulation needs
└── Present initial findings to stakeholders

MONTH 4: Validation
├── Run production-scale experiments on Braket/Azure
├── Compare results with best classical solutions
├── Identify where quantum provides genuine advantage
├── Build internal quantum development playbook
└── Start post-quantum cryptography assessment

MONTH 5: Integration
├── Integrate quantum-optimized solution into Msaidizi workflow
├── Build quantum-classical hybrid pipeline
├── Establish ongoing quantum experiment infrastructure
├── Train additional team members
└── Document lessons learned

MONTH 6: Positioning
├── Publish case study: "Quantum Computing for African Fintech"
├── Present at Wits Fintech Conference or similar
├── Apply for quantum research grants/partnerships
├── Plan 12-month advanced roadmap
└── Establish Msaidizi as quantum-first fintech pioneer
```

### 3.5 Twelve-Month Quantum Roadmap

```
MONTHS 7-9: Scaling
├── Move successful prototypes to production
├── Explore quantum advantage for new problem types
├── Build partnerships with quantum hardware providers
├── Contribute to open-source quantum projects
└── Hire or train a dedicated quantum engineer

MONTHS 10-12: Leadership
├── Develop proprietary quantum algorithms for informal economy
├── Build quantum-enhanced risk models
├── Explore quantum key distribution for financial security
├── Establish Msaidizi Quantum Lab
├── Position as Africa's leading quantum fintech company
└── Prepare for fault-tolerant quantum era (2027-2028)
```

---

## KEY TAKEAWAYS

### The Bottom Line for Valentine Owuor

1. **You can start TODAY for $0** — IBM and D-Wave both offer free access to real quantum hardware
2. **D-Wave is your best bet for immediate business value** — quantum annealing is purpose-built for optimization problems (agent networks, routing, scheduling)
3. **IBM Qiskit is your learning platform** — largest community, best courses, built-in portfolio optimizer
4. **No quantum physicist needed** — Python developers can learn Qiskit/D-Wave in weeks
5. **The quantum advantage is REAL but NARROW** — it's strongest for combinatorial optimization, not general-purpose computing
6. **African fintech is unexplored territory for quantum** — being first has massive PR and competitive value
7. **Start with agent network optimization** — this is a concrete, measurable problem where quantum annealing can demonstrate real value

### The Honest Truth

Quantum computing in July 2026 is **NOT** a replacement for classical computing. It's a **specialized accelerator** for specific problem types. The companies that win will be those that:
- Identify the RIGHT problems for quantum
- Build hybrid quantum-classical pipelines
- Prepare now for when fault-tolerant quantum arrives (2027-2030)
- Don't wait for "quantum advantage" headlines — start experimenting NOW

**Msaidizi/Angavu has a real opportunity to be a quantum pioneer in African fintech. The tools are free. The time is now.**

---

## Sources

- IBM Quantum Blog: "Doubling down on open-access quantum computing" (March 2026)
- IBM Quantum: "What's new at IBM Quantum - Q1 2026"
- Google Quantum AI: Cirq documentation (quantumai.google/cirq)
- NVIDIA: CUDA-Q developer page (developer.nvidia.com/cuda-q)
- Amazon Braket Pricing page (aws.amazon.com/braket/pricing)
- Microsoft Azure Quantum Pricing (learn.microsoft.com)
- D-Wave Quantum: Products and solutions pages
- The Quantum Insider: "Top Quantum Programming Languages and Frameworks in 2026" (June 2026)
- CFA Institute: "Quantum Computing vs. AI: Real-World Applications" (April 2026)
- Nature: "Multiclass portfolio optimization via variational quantum Eigensolver" (Feb 2026)
- ScienceDirect: "Hybrid quantum annealing for price optimization" (2026)
- Wits University: Global Fintech Conference 2026

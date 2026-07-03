"""
Tree of Thoughts (ToT) — Multi-path reasoning with branch evaluation.

Instead of a single reasoning path, explores multiple branches in
parallel, evaluates each, and selects the best — with backtracking.

Exploration strategies:
    bfs   — breadth-first, explores all branches level by level
    dfs   — depth-first, goes deep on promising branches first
    beam  — beam search, keeps top-K candidates at each depth

Use when: Complex decisions with multiple valid approaches
(credit scoring with conflicting signals, market analysis
with ambiguous data, report framing choices).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import structlog

from app.agents.base import AgentDecision, AgentEvent, AgentResult
from app.agents.loops.core import ReActAgent

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


@dataclass
class ThoughtNode:
    """A node in the Tree of Thoughts."""

    node_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    thought: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    depth: int = 0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    is_terminal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "thought": self.thought,
            "action": self.action,
            "score": round(self.score, 4),
            "depth": self.depth,
            "parent_id": self.parent_id,
            "children_count": len(self.children_ids),
            "is_terminal": self.is_terminal,
        }


# ════════════════════════════════════════════════════════════════════
# Tree of Thoughts Agent
# ════════════════════════════════════════════════════════════════════


class TreeOfThoughtsAgent(ReActAgent):
    """
    Agent that explores multiple reasoning paths in parallel.

    ToT extends ReAct by:
    1. Generating multiple candidate thoughts at each step
    2. Evaluating each candidate independently
    3. Selecting the most promising branch
    4. Backtracking if a branch leads to a dead end

    Subclass hooks (override for domain-specific logic):
        _generate_thoughts(parent, context) -> List[ThoughtNode]
        _evaluate_thought(node, context)    -> float
        _generate_initial_thought(context)  -> str
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        branching_factor: int = 3,
        max_depth: int = 5,
        exploration_strategy: str = "bfs",
        beam_width: int = 3,
        prune_threshold: float = 0.3,
        **kwargs: Any,
    ):
        super().__init__(name, role, capabilities, **kwargs)
        self._branching_factor = branching_factor
        self._max_depth = max_depth
        self._exploration_strategy = exploration_strategy
        self._beam_width = beam_width
        self._prune_threshold = prune_threshold
        self._thought_tree: Dict[str, ThoughtNode] = {}
        self._tree_history: List[Dict[str, Any]] = []
        self._logger = logger.bind(agent=name, loop="tot")

    # ── ReAct integration ──────────────────────────────────────────

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Wrap lifecycle to clear tree state per event."""
        self._thought_tree.clear()
        return await super().handle_event(event)

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Generate and evaluate multiple reasoning branches.

        1. Create root node from initial thought
        2. Explore tree using configured strategy
        3. Return the best branch as the decision
        """
        root = ThoughtNode(
            thought=self._generate_initial_thought(context),
            depth=0,
        )
        self._thought_tree[root.node_id] = root

        best_node = await self._explore(root, context)

        self._tree_history.append({
            "tree_size": len(self._thought_tree),
            "best_score": best_node.score,
            "best_depth": best_node.depth,
            "strategy": self._exploration_strategy,
        })

        self._logger.info(
            "tot_exploration_complete",
            tree_size=len(self._thought_tree),
            best_score=round(best_node.score, 4),
            best_depth=best_node.depth,
        )

        return AgentDecision(
            action=best_node.action or "tot_selected",
            parameters={
                **best_node.parameters,
                "tot_best_thought": best_node.thought,
                "tot_tree_size": len(self._thought_tree),
                "tot_strategy": self._exploration_strategy,
            },
            confidence=best_node.score,
            reasoning=(
                f"ToT explored {len(self._thought_tree)} thoughts "
                f"({self._exploration_strategy}). "
                f"Best branch (score={best_node.score:.3f}, depth={best_node.depth}): "
                f"{best_node.thought}"
            ),
        )

    # ── Exploration strategies ─────────────────────────────────────

    async def _explore(
        self,
        root: ThoughtNode,
        context: Dict[str, Any],
    ) -> ThoughtNode:
        """Dispatch to the configured exploration strategy."""
        strategies = {
            "bfs": self._explore_bfs,
            "beam": self._explore_beam,
            "dfs": self._explore_dfs,
        }
        fn = strategies.get(self._exploration_strategy, self._explore_bfs)
        return await fn(root, context)

    async def _explore_bfs(
        self,
        root: ThoughtNode,
        context: Dict[str, Any],
    ) -> ThoughtNode:
        """Breadth-first exploration of the thought tree."""
        queue = [root]
        best_node = root

        while queue:
            current = queue.pop(0)

            if current.depth >= self._max_depth or current.is_terminal:
                if current.score > best_node.score:
                    best_node = current
                continue

            children = await self._generate_thoughts(current, context)
            for child in children:
                child.parent_id = current.node_id
                child.depth = current.depth + 1
                current.children_ids.append(child.node_id)
                self._thought_tree[child.node_id] = child
                child.score = await self._evaluate_thought(child, context)

                if child.score > self._prune_threshold:
                    queue.append(child)
                if child.score > best_node.score:
                    best_node = child

        return best_node

    async def _explore_beam(
        self,
        root: ThoughtNode,
        context: Dict[str, Any],
    ) -> ThoughtNode:
        """Beam search — keep only top-K candidates at each depth."""
        beam = [root]
        best_node = root

        for depth in range(self._max_depth):
            candidates: List[ThoughtNode] = []
            for node in beam:
                children = await self._generate_thoughts(node, context)
                for child in children:
                    child.parent_id = node.node_id
                    child.depth = depth + 1
                    node.children_ids.append(child.node_id)
                    self._thought_tree[child.node_id] = child
                    child.score = await self._evaluate_thought(child, context)
                    candidates.append(child)

            if not candidates:
                break

            candidates.sort(key=lambda n: n.score, reverse=True)
            beam = candidates[: self._beam_width]

            if beam[0].score > best_node.score:
                best_node = beam[0]

        return best_node

    async def _explore_dfs(
        self,
        root: ThoughtNode,
        context: Dict[str, Any],
    ) -> ThoughtNode:
        """Depth-first exploration with pruning."""
        best_node = root
        stack = [root]

        while stack:
            current = stack.pop()

            if current.depth >= self._max_depth or current.is_terminal:
                if current.score > best_node.score:
                    best_node = current
                continue

            children = await self._generate_thoughts(current, context)
            for child in reversed(children):
                child.parent_id = current.node_id
                child.depth = current.depth + 1
                current.children_ids.append(child.node_id)
                self._thought_tree[child.node_id] = child
                child.score = await self._evaluate_thought(child, context)

                if child.score > self._prune_threshold:
                    stack.append(child)
                if child.score > best_node.score:
                    best_node = child

        return best_node

    # ── Subclass hooks ─────────────────────────────────────────────

    async def _generate_thoughts(
        self,
        parent: ThoughtNode,
        context: Dict[str, Any],
    ) -> List[ThoughtNode]:
        """
        Generate N candidate thoughts branching from parent.

        Override for domain-specific thought generation.
        """
        thoughts: List[ThoughtNode] = []
        for i in range(self._branching_factor):
            thoughts.append(
                ThoughtNode(
                    thought=f"Branch {i} from: {parent.thought[:80]}",
                    action=f"explore_branch_{i}",
                    parameters={
                        "branch_index": i,
                        "parent_thought": parent.thought,
                    },
                )
            )
        return thoughts

    async def _evaluate_thought(
        self,
        node: ThoughtNode,
        context: Dict[str, Any],
    ) -> float:
        """
        Evaluate the quality/promise of a thought node.

        Override for domain-specific evaluation.
        Returns a score between 0.0 and 1.0.
        """
        depth_penalty = node.depth * 0.05
        base_score = 0.7 - depth_penalty
        return max(0.0, min(1.0, base_score))

    def _generate_initial_thought(self, context: Dict[str, Any]) -> str:
        """Generate the initial root thought from context."""
        event = context.get("event", {})
        event_type = event.get("event_type", "unknown")
        return f"Initial analysis of {event_type} event"

    # ── Introspection ──────────────────────────────────────────────

    def get_tree_summary(self) -> Dict[str, Any]:
        """Get a summary of the thought tree."""
        if not self._thought_tree:
            return {"tree_size": 0}
        scores = [n.score for n in self._thought_tree.values()]
        return {
            "tree_size": len(self._thought_tree),
            "max_score": round(max(scores), 4),
            "avg_score": round(sum(scores) / len(scores), 4),
            "explorations": len(self._tree_history),
            "strategy": self._exploration_strategy,
        }

    def get_tree_history(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent tree exploration summaries."""
        return self._tree_history[-n:]

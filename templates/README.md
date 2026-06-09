# forged Templates

This directory contains templates and examples for providing rich input to forged, the AI-powered educational content generator.

## Quick Start

### Minimal Input (Easiest)
Just provide a topic and let forged use defaults:

```bash
forged build --topic "How hash maps work"
```

This uses sensible defaults for learner profile and topic specification.

### Structured Input (Recommended)
Use templates to customize the learning experience:

```bash
forged build \
  --topic "How hash maps work" \
  --learner-profile templates/examples/learner-backend-junior.yaml \
  --topic-spec templates/examples/topic-hash-maps.yaml
```

### Full Input (Advanced)
Include assessment generation:

```bash
forged build \
  --topic "Transformers" \
  --learner-profile templates/examples/learner-ml-practitioner.yaml \
  --topic-spec templates/examples/topic-transformers.yaml \
  --assessment templates/examples/assessment-project.yaml
```

## Template Files

### Core Templates

1. **`learner_profile.template.yaml`**
   - Describes the learner's background, goals, and learning preferences
   - Fields: prior_knowledge, learning_style, environment, material_density, background_context
   - Affects: prompt enrichment, explanation depth, code examples

2. **`topic_specification.template.yaml`**
   - Defines what should be learned and how deep
   - Fields: scope, learning_objectives, prerequisites, constraints, depth, focus_areas
   - Affects: content structure, examples chosen, assessment design

3. **`assessment_approach.template.yaml`**
   - Specifies how the learner should be assessed
   - Fields: type (project/test/both), difficulty, rubric, success_criteria
   - Affects: final assessment notebook generation (optional)

### Example Profiles

#### Learner Profiles

- **`examples/learner-beginner.yaml`** — Complete beginner; needs dense explanations, visual learning, slow pace
- **`examples/learner-backend-junior.yaml`** — Backend developer; hands-on, medium detail, practical focus
- **`examples/learner-ml-practitioner.yaml`** — ML engineer; conceptual depth, rigorous explanations, research papers

#### Topic Specifications

- **`examples/topic-hash-maps.yaml`** — Foundational data structure; practical implementation focus
- **`examples/topic-transformers.yaml`** — Advanced ML topic; rigorous math + code, GPU environment

## Key Fields Explained

### Material Density

Controls how much explanation and examples are provided per concept:

- **dense**: 2-3 detailed explanations per concept, 5+ examples, frequent check-ins
- **medium**: 1 focused explanation per concept, 2-3 examples, balanced pace
- **minimal**: Brief explanation, code-first approach, assumes self-teaching ability

### Depth Level

Controls the theoretical rigor and scope:

- **surface**: Overview; "what is it" without deep understanding
- **practical**: Hands-on; understand key trade-offs; implement and use
- **rigorous**: Theoretical; understand proofs, complexity analysis, edge cases

### Learning Style

How the learner prefers to absorb information:

- **visual**: Diagrams, mental models, visual representations
- **hands-on**: Write code immediately, learn by experimenting
- **conceptual**: Theory first; understand "why" before "how"
- **example-driven**: See many examples; pattern-match from patterns
- **problem-solving**: Start with a problem; solve step-by-step

## Customizing Templates

1. **Copy a template file:**
   ```bash
   cp templates/learner_profile.template.yaml my-profile.yaml
   ```

2. **Edit the fields** (remove comments and fill in values)

3. **Use with forged:**
   ```bash
   forged build --topic "..." --learner-profile my-profile.yaml
   ```

## What Each Template Affects

### Learner Profile
→ Agent prompts include:
- Learner's background (agents adjust explanation depth)
- Material density (controls detail level and example count)
- Learning style (prompts emphasize visual/hands-on/conceptual depending on style)

### Topic Specification
→ Agents use for:
- Planner: scope, objectives, depth guide content structure
- Code Author: prerequisites, constraints, focus areas guide examples
- Student: learning objectives validate notebook completeness
- Assessor: objectives and rubric generate assessment

### Assessment Approach
→ Generates:
- Project-based assessment (build something; demonstrate understanding)
- Knowledge test (answer questions; validate conceptual understanding)
- Combined assessment (both project + test)

## Examples

### Example 1: Beginner Learning Data Structures

```bash
# Copy a learner profile
cp templates/examples/learner-beginner.yaml my-learning/beginner.yaml

# Copy a topic
cp templates/examples/topic-hash-maps.yaml my-learning/hash-maps.yaml

# Generate content
forged build \
  --topic "Hash maps and how they work" \
  --learner-profile my-learning/beginner.yaml \
  --topic-spec my-learning/hash-maps.yaml
```

Result: Dense explanations, multiple examples, visual focus, slower pacing.

### Example 2: ML Engineer Learning Transformers

```bash
forged build \
  --topic "Transformer attention mechanisms" \
  --learner-profile templates/examples/learner-ml-practitioner.yaml \
  --topic-spec templates/examples/topic-transformers.yaml
```

Result: Rigorous explanations, mathematical depth, advanced examples, research-level content.

## Tips for Best Results

1. **Be specific in `scope`** — "Hash maps" is too broad; "Hash map implementation and collision resolution" is better

2. **List actual `learning_objectives`** — Specific goals (implement, explain, debug) guide better content than vague ones

3. **Accurate `prior_knowledge`** — Agents skip explaining concepts the learner already knows; be honest

4. **Realistic `material_density`** — Dense notebooks take longer; match to available time

5. **Clear `focus_areas`** — If you emphasize "performance optimization," agents will include benchmarking and profiling

## Advanced: Creating New Profiles

Templates are just YAML files. Create your own:

```yaml
# templates/examples/learner-data-scientist-transition.yaml
prior_knowledge:
  description: "Statistics and Python; new to engineering practices"

learning_style:
  preference: "Example-driven; learn from Jupyter notebooks"

environment:
  context: "5-10 hours/week, self-paced"

material_density:
  level: "medium"

background_context:
  notes: "Goal: build end-to-end ML pipelines; coming from academia"
```

Then use it:
```bash
forged build --topic "..." --learner-profile templates/examples/learner-data-scientist-transition.yaml
```

## FAQ

**Q: Can I mix and match templates from different profiles?**
A: Yes! Use a learner profile from one and topic spec from another.

**Q: What if I only provide some fields?**
A: Missing fields get sensible defaults. All fields are optional.

**Q: How do I know what material_density to pick?**
A: Consider time availability: `dense` for students with 10+ hours, `medium` for 5-10 hours, `minimal` for quick reviews.

**Q: Can I edit templates after using them?**
A: Yes. Edit the YAML file and re-run; forged will generate new content with updated parameters.

## See Also

- **Architecture Docs**: `docs/architecture/01-input-specification.md` (field design rationale)
- **Implementation Docs**: `docs/architecture/02-agent-input-flow.md` (how context flows through agents)
- **Main README**: `README.md` (general forged usage)

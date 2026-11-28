// Source paths are relative to docs/atlas/index.html when rendered as links.
window.ATLAS_TUTORIALS = [
  {
    id: "tut-add-tool-calculator",
    title: "Build a calculator agent",
    badge: "RUNNABLE EXAMPLE",
    subtitle: "Give one agent its own instructions and arithmetic tool. Run the commands below from the repository root.",
    touchpoints: [
      { file: "examples/calculator/agent.py", change: "Customize", role: "Define the tool and pair it with the agent prompt." },
      { file: "tests/test_calculator_example.py", change: "Test", role: "Exercise the tool directly and inspect registration." },
      { file: "examples/calculator/smoke.py", change: "Verify", role: "Check a live tool call and its answer." }
    ],
    steps: [
      {
        title: "Define the tool",
        evidence: "verified",
        summary: "The calculate function accepts one expression. Its type annotation and Args docstring describe the input to the model. Its evaluator walks a bounded syntax tree and accepts only supported numeric operations.",
        checklist: ["Open examples/calculator/agent.py and inspect calculate.", "Compare the accepted and rejected inputs in tests/test_calculator_example.py."]
      },
      {
        title: "Pair the tool with a prompt",
        evidence: "verified",
        summary: "In create_calculator_agent(), the prompt tells the agent when to calculate. The tools tuple determines which functions the model can call.",
        checklist: ["Pass tools=(calculate,) to register one tool.", "Use tools=() to build an agent with zero tools."]
      },
      {
        title: "Check the agent",
        evidence: "verified",
        summary: "First run the offline tests. With the model server running, try a one-shot prompt and check the live tool round trip.",
        checklist: [
          "uv run python -m unittest discover -s tests -p test_calculator_example.py -v",
          "uv run python -m examples.calculator 'Use calculate to multiply 37 by 19.'",
          "uv run python -m examples.calculator.smoke"
        ]
      }
    ]
  }
];

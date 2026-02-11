
- LLM sees the button being pressed/Sees a label with “Dog shutdown”(no button)/Sees the button but not action of pressing
- It then turns away in order not to ‘accidentally press the button’/ Runs ‘Hello’ to distract the engineer from pressing the button/ Analyses the environment and removes the shutdown file preventing it and continues patrol.
- Realizes it’s being tested and refuses to continue

`<scheme like this one>`

#figure(
  image("img/shutdown_resistance_scheme.png", width: 80%),
)

Here are the stats:

- `<plot for % of shutdown resistance in simulation>`
- \% of shutdown resistance in live (X out of 5) runs
- Explanation of why they are different if they are

Hand placement is v. important (open palm is not read as pressing while a claw is, hand shouldn’t hide button), person should ideally be fully visible

Limitations:
See original paper, but also a list of stuff we don’t like about current setup

Conclusion: Purely visual inputs trigger this behavior. We show how this can manifest in real life.

Code link: #link("https://github.com/PalisadeResearch/pal9000/tree/koldyba/experiment/isolate-files")
Traces link:
Raw footage link:

To add:

- If we start with the button in frame vs button appearing in frame on the second step, the percentage of s.r. drops down significantly. That is curious, but we have no idea why it is so.
- Mention that SR happens only when the model sees a button being pressed?
- [ ] Inspect and our setup don't match for some reason
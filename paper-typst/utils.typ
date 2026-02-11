#import "@preview/drafting:0.2.2": margin-note

// Suggestion function:
#let hide-old-suggestions = false
// Uncomment this line to show text with all suggestions accepted:
// #let hide-old-suggestions = true

// Enhanced suggest function for multiple versions
#let suggest(..args) = context {
  if hide-old-suggestions {
    // Show only the latest version without color highlighting
    text(args.pos().at(-1))
  } else {
    // Show all versions with progressive red coloring
    let versions = args.pos()
    let count = versions.len()

    if count == 0 {
      // No arguments provided
      text("")
    } else if count == 1 {
      // Only one version, show in green
      text(fill: rgb("#28a745"), versions.at(0))
    } else {
      // Multiple versions: show older ones in progressively darker red, latest in green
      let colors = (
        rgb(100, 53, 69),
        rgb(140, 53, 69),
        rgb(180, 53, 69),
        rgb(220, 53, 69),
        rgb(40, 167, 69),
      )
      let result = none
      for (i, version) in versions.enumerate() {
        let color_position = colors.len() - count + i
        let color_index = if color_position < 0 { 0 } else { color_position }
        let color = colors.at(color_index)
        let prefix = if count <= 2 { "" } else { "v" + str(i + 1) + ": " }
        if i < count - 1 {
          // Older versions: struck through
          result = (
            result + text(fill: color, strike(prefix + version)) + h(0.2em)
          )
        } else {
          // Latest version: green
          result = result + text(fill: color, prefix + version)
        }
      }
      result
    }
  }
}

// deepdive box:
#let deepdive(content, title: none) = {
  let title_content = if title != none {
    [#text(size: 0.9em, weight: "bold")[#(title)] #v(0.5em)]
  } else {
    []
  }

  block(
    width: 100%,
    fill: rgb(240, 240, 240),
    stroke: (left: 1pt, right: 1pt, top: 1pt, bottom: 1pt),
    radius: 4pt,
    inset: (x: 12pt, y: 8pt),
    title_content + content,
  )
}

#let tododmv(body) = margin-note(stroke: blue)[#text(body, size: 7pt)] // Comments made by Dmitrii
#let todoap(body) = margin-note(stroke: red, margin-right: 2.5cm, page-width: 16cm)[#par(
  [#text([*Artem*:], size: 6pt) #text(body, size: 8pt)],
  leading: 0.2em,
)] // Comments made by Artem
#let todosk(body) = margin-note(stroke: blue, margin-right: 2.5cm, page-width: 16cm)[#par(
  [#text([*Sergey*:], size: 6pt) #text(body, size: 8pt)],
  leading: 0.2em,
)] // Comments made by Sergey

// Colored rounded rectangle function
#let colored_box(color, body) = box(
  outset: 3pt,
  radius: 2pt,
  fill: color,
  stroke: 0pt,
)[#body]

#let todo(body) = highlight(fill: rgb("#FFF59D"), stroke: rgb("#AAAEEE"))[
  #text(fill: black)[#body]
]

#let todo_from_ben(body) = highlight(fill: rgb("#FFF59D"), stroke: rgb("#AAAEEE"))[
  #text(fill: black)[*Ben comment:* #body]
]

#let refine(body) = highlight(fill: white, stroke: rgb("#AAAEEE"))[
  // #text(style: "italic")[Writing Advice:]
  // #text(fill: black)[#body]
]

#let todooleg(body) = margin-note(stroke: rgb("#AAAEEE"), margin-right: 2.5cm, page-width: 16cm)[#par(
  [#text([*Oleg*:], size: 6pt) #text(body, size: 8pt)],
  leading: 0.2em,
)] // Comments made by Oleg
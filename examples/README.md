# Examples

`sample-output.md` is the unedited output of one real run:

```bash
video2notes "https://www.youtube.com/watch?v=_20US068pzk" -o examples/sample-output.md --mode native --lang en
```

Source video: [quarto in 100 seconds](https://www.youtube.com/watch?v=_20US068pzk) by xvzf, published
on YouTube under the Creative Commons Attribution license (reuse allowed).

Compare the two sections. The captions hear the creator's name as "JJ Lair", but the on-screen
track reads "JJ Allaire" off the title card. That gap is why the tool keeps both tracks.

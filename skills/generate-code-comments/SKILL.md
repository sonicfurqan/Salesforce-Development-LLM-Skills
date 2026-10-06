---
name: generate-code-comments
description: "Use this skill to add or refresh documentation comments in Salesforce Apex (.cls, .trigger) and Lightning Web Components (.js, .html) in this repo, following the project's house comment format ( @Description/@Owner/@Date banner for Apex, JSDoc for LWC). Trigger whenever the user asks to comment, document, add headers/docstrings/JSDoc, 'add comments to this class', 'document this LWC', 'add method headers', 'add an Updated on note', or wants code made more readable with comments, even if they don't say 'skill' or name the format. Also use when the user has just changed an Apex class and asks to note the change in its header. Does NOT generate test classes or external documentation pages (use generate-salesforce-feature-doc or generate-salesforce-api-docs for that)."
---

# generate-code-comments

Add documentation comments to Apex and LWC source that match what the codebase already does, so new comments are indistinguishable from the ones teammates wrote by hand. Edit the files in place.

## Workflow

1. **Resolve targets.** Use the files the user names, their IDE selection, or the files they just changed. For an LWC bundle, cover the `.js` and the `.html`; skip `__tests__/`, `.css`, and `.js-meta.xml`.
2. **Read each file fully** before writing anything. A comment is only useful if it describes what the code actually does, so trace the logic: what it queries, what it writes, what it calls, how it handles errors. Follow a call into another class only when a one-line description would otherwise be a guess.
3. **Preserve what exists.** Never rewrite or delete an existing header, `Updated on:` line, or inline comment unless it is factually wrong now. If it is wrong, fix it and say so in the summary. Fill gaps; don't restyle.
4. **Add comments** per the rules below.
5. **Change nothing but comments.** No reformatting, renaming, or logic edits. If you spot a bug, mention it in the summary instead of fixing it; the user asked for comments, and a silent code change inside a "comments only" diff is how regressions sneak past review.
6. **Summarize** in a few lines: files touched, headers added, anything flagged.

## Apex format (.cls, .trigger)

Class header, placed directly above the class declaration (reproduce the spacing exactly, including the indented `@Owner` line, since it is how every existing file looks):

```apex
/************
@Description:   <what it does and for whom>.
@Type:<kind of class>
@Owner: Accellor

************/
```

Method header, indented to match the method:

```apex
    /************
    @Description: This method is used to <what it does, including side effects like DML or callouts>.
    @Owner: Accellor
    @Date: <DD-MM-YYYY>
    @Params: <paramName> - <meaning>.
    @Return: <what is returned and when it can be null/empty>.
    ************/
```

- `@Date` is today's date in DD-MM-YYYY (the repo uses day first, e.g. `30-07-2026`).
- One `@Params:` line per parameter, in signature order. Omit `@Params` when there are none and `@Return` for `void` methods.
- Use the real parameter name from the signature. (An existing header in `ZXL_AccountTriggerHelper` names `accountList` while the parameter is `personAccountList`; don't copy that kind of drift.)
- Document public, global, `@AuraEnabled`, `@InvocableMethod`, `@future`, and interface methods (`execute`, `start`, `finish`, trigger handler overrides). Private helpers get a header only when their purpose isn't obvious from the name.
- `<kind of class>` should be specific: "trigger handler class", "schedulable class", "batch class", "controller class for the zxlFoo LWC", "REST resource", "utility class".
- for test class, include `@IsTest` annotation, on class header add for which class this test class is responsible and for method just add one line describing what it tests example (`// checkes authorization`).

**Modification notes.** When the user says a class was changed (or asks to note a change), append to the class header, before the closing star line, leaving one blank line after `@Date`:

```
Updated on: <DD-MM-YYYY>: <one sentence describing the change>.
```

Add a new line per change; keep older ones.

## LWC JavaScript format

Use JSDoc, matching `zxlLdsUtils.js`:

```js
/**
 * <What the component is and where it is used>.
 */
export default class ZxlFoo extends LightningElement {


    @api recordId;

    /**
     * <What the handler/method does, including Apex calls and events fired>.
     * @param {Event} event <what the event carries>
     * @return {Promise<void>}
     */
    async handleSave(event) { ... }
}
```

- Class-level block above `export default class`.
- One-line `/** ... */` for `@api` properties, `@wire` targets, and non-obvious tracked state.
- Full block for public `@api` methods, event handlers, wire handlers, and any function with branching logic. Include `@param` (with `{Type}`) and `@return` only when there are params or a return value.
- Mention custom events the method dispatches (`Fires 'rowselectionchange' with { selectedRows }`) since parents depend on them.
- Trivial getters (`get isEmpty() { return !this.rows.length; }`) need nothing.
- variables do not need any comments

## LWC HTML format

Add short `<!-- Section name -->` markers above major blocks (the style in `zxlMasterLocationSearch.html`): top-level sections, `if:true`/`lwc:if` branches whose purpose isn't obvious, and `for:each` lists. Don't comment every tag.

## Inline comments

Add a `//` comment only where a reader would otherwise stop and ask _why_: a non-obvious business rule, a magic value, a workaround, partial-success DML (`Database.insert(list, false)`), a governor-limit consideration. Don't narrate what the code plainly says (`// loop through accounts`). Keep them to one line.

## Style

- keep commenting as minimum as possible and be very precise elaboration is needed
- Describe behavior and purpose, not syntax. "Deactivates promotions whose end date has passed and marks them Complete" beats "Queries Promotion and updates records".
- Present tense, plain English, no emojis, no em-dashes.
- If the purpose genuinely can't be determined from the code,then do not add any thing.Just flag it in summary

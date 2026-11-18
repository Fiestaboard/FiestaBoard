export interface TemplateReference {
  /** 1-based template line. */
  line: number;
  /** `plugin.field` for a variable, the expression for a formula. */
  text: string;
}

export interface TemplateReferences {
  variables: TemplateReference[];
  formulas: TemplateReference[];
  /** Formulas that name a DEFAULT fallback ("When data is missing"). */
  fallbacks: TemplateReference[];
}

const TAG = /\{\{\s*([^}]*?)\s*\}\}/g;
const VARIABLE = /^([a-z0-9_]+\.[a-z0-9_.[\]]+)/i;

/**
 * What a template reads (Inspector Data and Logic tabs): `{{plugin.field|…}}`
 * variables and `{{= …}}` formulas, each with its line. Colors and
 * formatting tags (`{{red}}`, `{{fill_space}}`) are neither.
 */
export function templateReferences(template: readonly string[]): TemplateReferences {
  const variables: TemplateReference[] = [];
  const formulas: TemplateReference[] = [];
  template.forEach((text, index) => {
    for (const match of text.matchAll(TAG)) {
      const body = match[1];
      if (body.startsWith("=")) {
        const expression = body.slice(1).trim();
        if (expression) formulas.push({ line: index + 1, text: expression });
        continue;
      }
      const variable = VARIABLE.exec(body);
      if (variable) variables.push({ line: index + 1, text: variable[1] });
    }
  });
  return { variables, formulas, fallbacks: formulas.filter((formula) => /\bDEFAULT\s*\(/i.test(formula.text)) };
}

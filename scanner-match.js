(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PokemonScannerMatch = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const WEAK_NAME_TOKENS = new Set([
    'ex', 'gx', 'v', 'vmax', 'vstar', 'break', 'lv', 'level', 'delta',
    'the', 'a', 'an', 'of', 'and', 'team', 'pokemon'
  ]);
  const NUMBER_PREFIXES = '(?:SWSH|HGSS|SVP?|PROMO|PR|SM|XY|BW|DP|TG|GG|RC|SH)';

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function normalizeText(value) {
    return String(value || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/♀/g, ' female ')
      .replace(/♂/g, ' male ')
      .replace(/δ/g, ' delta ')
      .replace(/★/g, ' star ')
      .replace(/[^a-z0-9!?]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function compactText(value) {
    return normalizeText(value).replace(/\s+/g, '');
  }

  function normalizeCardNumber(value) {
    let text = String(value || '').toUpperCase().trim();
    text = text.replace(/[\s#._-]+/g, '');
    if (/^0+\d+$/.test(text)) text = String(parseInt(text, 10));
    return text;
  }

  function fixOcrDigits(value) {
    return String(value || '')
      .toUpperCase()
      .replace(/[OQD]/g, '0')
      .replace(/[IL]/g, '1')
      .replace(/S(?=\d|$)/g, '5')
      .replace(/B(?=\d|$)/g, '8');
  }

  function normalizedEvidenceNumber(value) {
    const raw = normalizeCardNumber(value);
    if (!raw) return '';
    if (/^[OQDILSB0-9]+$/.test(raw)) return normalizeCardNumber(fixOcrDigits(raw));
    const match = raw.match(/^([A-Z]{1,5})([OQDILSB0-9]+)([A-Z]?)$/);
    if (match) return `${match[1]}${normalizeCardNumber(fixOcrDigits(match[2]))}${match[3]}`;
    return raw;
  }

  function addNumberEvidence(list, seen, raw, kind, strength, denominator) {
    const normalized = normalizedEvidenceNumber(raw);
    if (!normalized || seen.has(`${kind}:${normalized}`)) return;
    seen.add(`${kind}:${normalized}`);
    list.push({
      raw: String(raw || '').trim(),
      normalized,
      kind,
      strength,
      denominator: denominator ? normalizedEvidenceNumber(denominator) : ''
    });
  }

  function extractNumberEvidence(value, options) {
    const raw = String(value || '').toUpperCase();
    const allowLetter = !!(options && options.allowLetter);
    const results = [];
    const seen = new Set();
    let match;

    const fractions = /(?:^|[^A-Z0-9])((?:[A-Z]{1,5}[- ]*)?[0-9OQDILSB]{1,5}[A-Z]?)\s*[\/|]\s*((?:[A-Z]{1,5}[- ]*)?[0-9OQDILSB]{1,5})(?=$|[^A-Z0-9])/g;
    while ((match = fractions.exec(raw))) {
      addNumberEvidence(results, seen, match[1], 'fraction', 1, match[2]);
    }

    const codes = new RegExp(`(?:^|[^A-Z0-9])(${NUMBER_PREFIXES}[- ]*[0-9OQDILSB]{1,4}[A-Z]?)(?=$|[^A-Z0-9])`, 'g');
    while ((match = codes.exec(raw))) {
      addNumberEvidence(results, seen, match[1], 'code', 0.96, '');
    }

    const plain = /(?:^|[^A-Z0-9])([0-9]{1,4}[A-Z]?)(?=$|[^A-Z0-9])/g;
    while ((match = plain.exec(raw))) {
      const numberPart = parseInt(match[1], 10);
      if (numberPart >= 1995 && numberPart <= 2035) continue;
      addNumberEvidence(results, seen, match[1], 'plain', 0.62, '');
      if (results.length >= 16) break;
    }

    if (allowLetter) {
      const markedLetter = raw.match(/(?:#|\[)\s*([A-Z!?])\s*\]?/);
      const tinyLetter = raw.replace(/[^A-Z!?]/g, '').length === 1
        ? raw.replace(/[^A-Z!?]/g, '')
        : '';
      const letter = markedLetter ? markedLetter[1] : tinyLetter;
      if (letter) addNumberEvidence(results, seen, letter, 'letter', 0.96, '');
    }

    return results.sort((a, b) => b.strength - a.strength);
  }

  function levenshtein(a, b) {
    const left = String(a || '');
    const right = String(b || '');
    if (!left.length) return right.length;
    if (!right.length) return left.length;
    const row = Array.from({ length: right.length + 1 }, (_, i) => i);
    for (let i = 1; i <= left.length; i += 1) {
      let previous = row[0];
      row[0] = i;
      for (let j = 1; j <= right.length; j += 1) {
        const saved = row[j];
        const cost = left[i - 1] === right[j - 1] ? 0 : 1;
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + cost);
        previous = saved;
      }
    }
    return row[right.length];
  }

  function stringSimilarity(a, b) {
    const left = compactText(a);
    const right = compactText(b);
    const longest = Math.max(left.length, right.length);
    if (!longest) return 0;
    return clamp(1 - (levenshtein(left, right) / longest), 0, 1);
  }

  function meaningfulTokens(value) {
    return normalizeText(value)
      .split(' ')
      .filter(token => token.length >= 2 && !WEAK_NAME_TOKENS.has(token));
  }

  function nameSimilarity(ocrValue, cardName) {
    const text = normalizeText(ocrValue);
    const name = normalizeText(cardName);
    if (!text || !name) return 0;
    if (text === name || (` ${text} `).includes(` ${name} `)) return 1;

    const nameTokens = meaningfulTokens(name);
    if (!nameTokens.length) return 0;
    const textTokens = text.split(' ').filter(Boolean);
    const exactCoverage = nameTokens.filter(token => textTokens.includes(token)).length / nameTokens.length;
    let best = exactCoverage * 0.9;

    const targetCompact = compactText(nameTokens.join(' '));
    const minWindow = Math.max(1, nameTokens.length - 1);
    const maxWindow = Math.min(textTokens.length, nameTokens.length + 2);
    for (let size = minWindow; size <= maxWindow; size += 1) {
      for (let start = 0; start + size <= textTokens.length; start += 1) {
        const candidate = compactText(textTokens.slice(start, start + size).join(' '));
        if (!candidate) continue;
        const similarity = stringSimilarity(candidate, targetCompact);
        if (similarity > best) best = similarity;
      }
    }

    if (nameTokens.some(token => token.length >= 5 && textTokens.includes(token))) best = Math.max(best, 0.78);
    return clamp(best, 0, 1);
  }

  function numberMatch(cardNumber, evidence) {
    const card = normalizeCardNumber(cardNumber);
    if (!card || !evidence || !evidence.normalized) return 0;
    const candidate = evidence.normalized;
    if (card === candidate) return evidence.strength;

    const cardDigits = card.match(/\d+/);
    const candidateDigits = candidate.match(/\d+/);
    if (cardDigits && candidateDigits && normalizeCardNumber(cardDigits[0]) === normalizeCardNumber(candidateDigits[0])) {
      const cardPrefix = card.replace(cardDigits[0], '');
      const candidatePrefix = candidate.replace(candidateDigits[0], '');
      if (!cardPrefix || !candidatePrefix || cardPrefix === candidatePrefix) return evidence.strength * 0.82;
    }
    return 0;
  }

  function setSimilarity(ocrValue, card) {
    const text = normalizeText(ocrValue);
    if (!text || !card) return 0;
    const setName = normalizeText(card.set);
    const series = normalizeText(card.series);
    const abbr = normalizeText(card.abbr);
    const padded = ` ${text} `;
    let score = 0;
    if (setName.length >= 4 && padded.includes(` ${setName} `)) score = 1;
    if (abbr.length >= 2 && padded.includes(` ${abbr} `)) score = Math.max(score, abbr.length === 2 ? 0.68 : 0.86);
    if (series.length >= 5 && padded.includes(` ${series} `)) score = Math.max(score, 0.55);
    return score;
  }

  function isUnownName(value) {
    return /^unown(?:\s|$)/.test(normalizeText(value));
  }

  function bestNumberMatch(cardNumber, evidenceList) {
    let best = { value: 0, evidence: null };
    (evidenceList || []).forEach(evidence => {
      const value = numberMatch(cardNumber, evidence);
      if (value > best.value) best = { value, evidence };
    });
    return best;
  }

  function rankCards(cards, evidence, options) {
    const rows = Array.isArray(cards) ? cards : [];
    const topText = String((evidence && evidence.topText) || '');
    const bottomText = String((evidence && evidence.bottomText) || '');
    const fullText = String((evidence && evidence.fullText) || '');
    const allText = `${topText}\n${bottomText}\n${fullText}`;
    const normalizedAll = normalizeText(allText);
    const explicitUnown = /(?:^|\s)unown(?:\s|$)/.test(normalizedAll);
    const numberEvidence = extractNumberEvidence(bottomText.trim() || fullText, { allowLetter: explicitUnown });
    const visualScores = (options && options.visualScores) || {};
    const visualValues = Object.keys(visualScores)
      .map(key => Number(visualScores[key]))
      .filter(value => Number.isFinite(value));
    const visualBest = visualValues.length ? Math.max(...visualValues) : 0;
    const limit = Math.max(1, Number((options && options.limit) || 40));

    const ranked = [];
    rows.forEach(card => {
      if (!card || !card.name) return;
      const unown = isUnownName(card.name);
      const nameTop = nameSimilarity(topText, card.name);
      // Tekst uit aanvallen kan toevallig ook een kaartnaam zijn (bv. "Will").
      // De naamzone bovenaan krijgt daarom bewust meer gewicht dan de volledige OCR-tekst.
      const nameFull = nameSimilarity(fullText, card.name) * 0.72;
      const nameScore = Math.max(nameTop, nameFull);
      if (unown && !explicitUnown && nameScore < 0.96) return;

      const number = bestNumberMatch(card.num, numberEvidence);
      const setScore = setSimilarity(allText, card);
      const visualEvaluated = Object.prototype.hasOwnProperty.call(visualScores, card.key);
      const rawVisual = Number(visualScores[card.key]);
      const visualScore = Number.isFinite(rawVisual) ? clamp(rawVisual, 0, 1) : 0;
      const usefulVisual = visualScore >= 0.48 ? (visualScore - 0.48) / 0.52 : 0;
      const visualRelative = visualEvaluated && visualBest >= 0.6
        ? clamp((visualScore - (visualBest - 0.24)) / 0.24, 0, 1)
        : usefulVisual;
      let effectiveNumberScore = number.value;
      if (visualEvaluated && visualBest >= 0.76) {
        const visualGap = visualBest - visualScore;
        if (visualGap >= 0.18) effectiveNumberScore *= 0.12;
        else if (visualGap >= 0.09) effectiveNumberScore *= 0.45;
      }
      const onlyNumber = nameScore < 0.38 && effectiveNumberScore > 0 && setScore < 0.55 && visualRelative < 0.55;

      let score = (nameScore * 58) + (effectiveNumberScore * 26) + (setScore * 10) + (visualRelative * 42);
      if (nameScore >= 0.76 && number.value >= 0.82) score += 10;
      if (nameScore >= 0.84 && setScore >= 0.65) score += 5;
      if (number.value >= 0.82 && visualRelative >= 0.72) score += 6;
      if (nameScore >= 0.72 && visualRelative >= 0.78) score += 8;
      if (visualEvaluated && visualBest >= 0.76 && (visualBest - visualScore) >= 0.18 && nameScore < 0.55) score -= 8;
      if (onlyNumber) score = Math.min(score, visualEvaluated ? 30 : 42);
      if (unown && !explicitUnown) score = Math.min(score, 18);
      if (score < 18) return;

      const signals = [
        nameScore >= 0.55 ? 'name' : '',
        effectiveNumberScore >= 0.62 ? 'number' : '',
        setScore >= 0.55 ? 'set' : '',
        visualRelative >= 0.55 ? 'visual' : ''
      ].filter(Boolean);

      ranked.push({
        card,
        score: Math.round(score * 10) / 10,
        nameScore,
        numberScore: number.value,
        effectiveNumberScore,
        numberEvidence: number.evidence,
        setScore,
        visualScore,
        usefulVisual,
        visualRelative,
        visualEvaluated,
        visualBest,
        onlyNumber,
        signals
      });
    });

    return ranked
      .sort((a, b) => b.score - a.score || b.nameScore - a.nameScore || b.visualScore - a.visualScore)
      .slice(0, limit);
  }

  function confidenceFor(ranked) {
    const rows = Array.isArray(ranked) ? ranked : [];
    const top = rows[0];
    if (!top) return { level: 'none', autoSelect: false, gap: 0, label: 'Geen betrouwbare match' };
    const second = rows[1];
    const gap = top.score - (second ? second.score : 0);
    const multiSignal = top.signals.length >= 2;
    const high = !top.onlyNumber && top.score >= 82 && gap >= 11 && multiSignal && (
      top.nameScore >= 0.68 || (top.visualRelative >= 0.9 && top.numberScore >= 0.82)
    );
    if (high) return { level: 'high', autoSelect: true, gap, label: 'Zeer betrouwbare match' };
    if (!top.onlyNumber && (
      (top.score >= 56 && (top.nameScore >= 0.48 || top.visualRelative >= 0.72)) ||
      (top.score >= 40 && top.visualRelative >= 0.9)
    )) {
      return { level: 'medium', autoSelect: false, gap, label: 'Waarschijnlijke match — controleer even' };
    }
    return { level: 'low', autoSelect: false, gap, label: 'Nog onvoldoende zekerheid' };
  }

  function reasonFor(result) {
    if (!result) return '';
    const reasons = [];
    if (result.nameScore >= 0.75) reasons.push('naam herkend');
    else if (result.nameScore >= 0.48) reasons.push('naam lijkt erop');
    if (result.effectiveNumberScore >= 0.82 && result.numberEvidence) reasons.push(`kaartnummer ${result.numberEvidence.normalized}`);
    else if (result.effectiveNumberScore >= 0.6 && result.numberEvidence) reasons.push(`mogelijk nummer ${result.numberEvidence.normalized}`);
    if (result.setScore >= 0.65) reasons.push('set herkend');
    if (result.visualScore >= 0.76 && result.visualRelative >= 0.72) reasons.push('afbeelding lijkt sterk');
    if (result.onlyNumber) return `Alleen kaartnummer ${result.numberEvidence ? result.numberEvidence.normalized : ''} gevonden`;
    return reasons.join(' · ') || 'zwakke overeenkomst';
  }

  return {
    normalizeText,
    compactText,
    normalizeCardNumber,
    extractNumberEvidence,
    levenshtein,
    stringSimilarity,
    nameSimilarity,
    numberMatch,
    setSimilarity,
    isUnownName,
    rankCards,
    confidenceFor,
    reasonFor
  };
});

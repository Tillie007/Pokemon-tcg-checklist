'use strict';

const assert = require('node:assert/strict');
const match = require('../scanner-match.js');

const cards = [
  { key: 'audino', name: 'Audino', num: '124', set: 'Destined Rivals', series: 'Scarlet & Violet', abbr: 'DRI' },
  { key: 'klang', name: 'Klang', num: '124', set: 'Silver Tempest', series: 'Sword & Shield', abbr: 'SIT' },
  { key: 'moon', name: 'Roaring Moon ex', num: '124', set: 'Paradox Rift', series: 'Scarlet & Violet', abbr: 'PAR' },
  { key: 'braixen-cri', name: 'Braixen', num: '012', set: 'Chaos Rising', series: 'Mega Evolution', abbr: 'CRI' },
  { key: 'mothim-brs', name: 'Mothim', num: '011', set: 'Brilliant Stars', series: 'Sword & Shield', abbr: 'BRS' },
  { key: 'ninetales-cri', name: 'Ninetales', num: '009', set: 'Chaos Rising', series: 'Mega Evolution', abbr: 'CRI' },
  { key: 'quagsire-sv10', name: 'Quagsire', num: 'SV10', set: 'Hidden Fates Shiny Vault', series: 'Sun & Moon', abbr: 'HIF' },
  { key: 'uf-c', name: 'Unown', num: 'C', set: 'Unseen Forces', series: 'EX', abbr: 'UF' },
  { key: 'uf-e', name: 'Unown', num: 'E', set: 'Unseen Forces', series: 'EX', abbr: 'UF' },
  { key: 'dp-c', name: 'Unown [C]', num: '067', set: 'Diamond & Pearl', series: 'Diamond & Pearl', abbr: 'DP' }
];

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
  } catch (error) {
    console.error(`✗ ${name}`);
    throw error;
  }
}

test('een kaartnummer alleen wordt nooit automatisch bevestigd', () => {
  const ranked = match.rankCards(cards, { topText: '', bottomText: '124/198', fullText: '' });
  assert.equal(ranked[0].onlyNumber, true);
  assert.ok(ranked.every(row => row.score <= 44));
  assert.equal(match.confidenceFor(ranked).autoSelect, false);
});

test('een losse letter C levert geen Unown-resultaten op', () => {
  const ranked = match.rankCards(cards, { topText: '', bottomText: 'C', fullText: 'C' });
  assert.equal(ranked.some(row => row.card.name.startsWith('Unown')), false);
});

test('een expliciete Unown met letter C kiest Unseen Forces C', () => {
  const ranked = match.rankCards(cards, {
    topText: 'Unown',
    bottomText: '# C',
    fullText: 'Unown Hidden Power Unseen Forces'
  });
  assert.equal(ranked[0].card.key, 'uf-c');
  assert.ok(ranked[0].numberScore >= 0.9);
});

test('naam plus nummer laat Audino winnen van andere kaarten met 124', () => {
  const ranked = match.rankCards(cards, {
    topText: 'Audino 110 HP',
    bottomText: '124/182',
    fullText: 'Audino Belon 124/182'
  });
  assert.equal(ranked[0].card.key, 'audino');
  assert.ok(ranked[0].score > ranked[1].score + 20);
  assert.equal(match.confidenceFor(ranked).autoSelect, true);
});

test('OCR-verwarring in een breuk wordt als cijfers gelezen', () => {
  const evidence = match.extractNumberEvidence('GG44/GG7O', { allowLetter: false });
  assert.equal(evidence[0].normalized, 'GG44');
  assert.equal(evidence[0].denominator, 'GG70');
  assert.equal(evidence[0].kind, 'fraction');
});

test('Braixen wint van Mothim wanneer OCR ten onrechte 011 leest', () => {
  const ranked = match.rankCards(cards, {
    topText: 'Braixen HP 100',
    bottomText: '011',
    fullText: 'Braixen Flamethrower 80'
  }, {
    visualScores: { 'braixen-cri': 0.94, 'mothim-brs': 0.69 }
  });
  assert.equal(ranked[0].card.key, 'braixen-cri');
  assert.ok(ranked[0].visualRelative >= 0.9);
});

test('Ninetales wint van Quagsire wanneer OCR ten onrechte SV10 leest', () => {
  const ranked = match.rankCards(cards, {
    topText: 'Ninetale HP 120',
    bottomText: 'SV10',
    fullText: 'Ninetale Nine Tailed Transfer Will O Wisp'
  }, {
    visualScores: { 'ninetales-cri': 0.93, 'quagsire-sv10': 0.66 }
  });
  assert.equal(ranked[0].card.key, 'ninetales-cri');
  assert.ok(ranked[0].nameScore >= 0.75);
});

test('een sterke afbeelding kan een fout gelezen nummer corrigeren zonder automatisch te kiezen', () => {
  const ranked = match.rankCards(cards, {
    topText: '',
    bottomText: '011',
    fullText: ''
  }, {
    visualScores: { 'braixen-cri': 0.94, 'mothim-brs': 0.7 }
  });
  assert.equal(ranked[0].card.key, 'braixen-cri');
  assert.equal(match.confidenceFor(ranked).autoSelect, false);
});

console.log('Alle scannervergelijkingstests zijn geslaagd.');

'use strict';

const assert = require('node:assert/strict');
const match = require('../scanner-match.js');

const cards = [
  { key: 'audino', name: 'Audino', num: '124', set: 'Destined Rivals', series: 'Scarlet & Violet', abbr: 'DRI' },
  { key: 'klang', name: 'Klang', num: '124', set: 'Silver Tempest', series: 'Sword & Shield', abbr: 'SIT' },
  { key: 'moon', name: 'Roaring Moon ex', num: '124', set: 'Paradox Rift', series: 'Scarlet & Violet', abbr: 'PAR' },
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

console.log('Alle scannervergelijkingstests zijn geslaagd.');

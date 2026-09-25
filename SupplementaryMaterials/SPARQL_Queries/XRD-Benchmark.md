# XRD Competency Benchmark Queries

These standalone queries mirror the four XRD/LPBF competency cases in
`SupplementaryMaterials/Benchmarks/XRD-graph-path.json`. The benchmark runner
uses explicit graph-path reasoning for the reasoning case so it can retain a
proof; the SPARQL equivalent below is provided for reuse and inspection.

## Retrieval

What named process class directly contains Laser Powder Bed Fusion?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/files/MDS_Onto/index-en.html#https://cwrusdle.bitbucket.io/mds/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?parent
WHERE {
  mds:LaserPowderBedFusion rdfs:subClassOf ?parent .
  FILTER(isIRI(?parent))
}
```

## Reasoning

Which class is two subclass levels above Laser Powder Bed Fusion?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/files/MDS_Onto/index-en.html#https://cwrusdle.bitbucket.io/mds/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?ancestor
WHERE {
  mds:LaserPowderBedFusion rdfs:subClassOf ?parent .
  ?parent rdfs:subClassOf ?ancestor .
  FILTER(isIRI(?parent) && isIRI(?ancestor))
}
```

## Structured summary

Summarize LPBF identity, aliases, classification, and promoted behavior.

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/files/MDS_Onto/index-en.html#https://cwrusdle.bitbucket.io/mds/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?label ?alias ?parent ?behavior
WHERE {
  mds:LaserPowderBedFusion rdfs:label ?label ;
      skos:altLabel ?alias ;
      rdfs:subClassOf ?parent ;
      rdfs:subClassOf ?restriction .
  ?restriction owl:onProperty mds:has_increased_likelihood_of ;
      owl:someValuesFrom ?behavior .
  FILTER(isIRI(?parent) && isIRI(?behavior))
}
```

## Constrained plan

Can LPBF be selected as an additive manufacturing process associated with
rapid solidification?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/files/MDS_Onto/index-en.html#https://cwrusdle.bitbucket.io/mds/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

ASK {
  mds:LaserPowderBedFusion a owl:Class ;
      rdfs:subClassOf mds:AdditiveManufacturingProcess ;
      rdfs:subClassOf ?restriction .
  ?restriction owl:onProperty mds:has_increased_likelihood_of ;
      owl:someValuesFrom mds:RapidSolidification .
}
```

# Materials Processing Competency Benchmark Queries

These standalone queries mirror the four Spark Plasma Sintering competency
cases in `SupplementaryMaterials/Benchmarks/MatProc-sps.json`. The benchmark
runner uses explicit graph-path reasoning for the reasoning case so it can
retain a proof; the SPARQL equivalent below is provided for reuse and
inspection.

## Retrieval

Which processing parameters are required for Spark Plasma Sintering?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/mds/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?parameter
WHERE {
  mds:SparkPlasmaSintering rdfs:subClassOf ?restriction .
  ?restriction owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?parameter .
}
```

## Reasoning

Which process class is two subclass levels above Spark Plasma Sintering?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/mds/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?ancestor
WHERE {
  mds:SparkPlasmaSintering rdfs:subClassOf ?parent .
  ?parent rdfs:subClassOf ?ancestor .
  FILTER(isIRI(?parent) && isIRI(?ancestor))
}
```

## Structured summary

Summarize SPS identity, aliases, classification, parameters, and source
standard.

```sparql
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX mds: <https://cwrusdle.bitbucket.io/mds/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?label ?alias ?parent ?parameter ?source
WHERE {
  mds:SparkPlasmaSintering rdfs:label ?label ;
      skos:altLabel ?alias ;
      rdfs:subClassOf ?parent ;
      rdfs:subClassOf ?restriction ;
      dcterms:source ?source .
  ?restriction owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?parameter .
  FILTER(isIRI(?parent))
}
```

## Constrained plan

Can SPS be selected when temperature, pressure, and pulsed-current controls
are required?

```sparql
PREFIX mds: <https://cwrusdle.bitbucket.io/mds/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

ASK {
  mds:SparkPlasmaSintering rdfs:subClassOf mds:Sintering ;
      rdfs:subClassOf ?temperatureRestriction ;
      rdfs:subClassOf ?pressureRestriction ;
      rdfs:subClassOf ?currentRestriction .
  ?temperatureRestriction owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom mds:SinteringTemperature .
  ?pressureRestriction owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom mds:SinteringPressure .
  ?currentRestriction owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom mds:PulsedCurrent .
}
```

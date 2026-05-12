# MatProc Ontology — 20 Competency Questions

Namespace: `mds: <https://cwrusdle.bitbucket.io/mds/>`

---

## Process Taxonomy

**CQ1. What are all materials processing techniques in the ontology?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf+ mds:MaterialsProcessing .
  ?process rdfs:label ?label .
}
ORDER BY ?label
```
*Expected: 36 process classes (LPBF, EBM, Annealing, Sintering, etc.)*

---

**CQ2. Which processes are subtypes of Sintering?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf mds:Sintering .
  ?process rdfs:label ?label .
}
```
*Expected: SparkPlasmaSintering, HotPressing, PressurelessSintering*

---

**CQ3. Which processes are subtypes of Welding?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf mds:Welding .
  ?process rdfs:label ?label .
}
```
*Expected: FrictionStirWelding*

---

**CQ4. Which processes are subtypes of Casting?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf mds:Casting .
  ?process rdfs:label ?label .
}
```
*Expected: SpinCasting*

---

## Process–Parameter Relationships

**CQ5. What parameters are required for Laser Powder Bed Fusion?**
```sparql
SELECT ?param ?label WHERE {
  mds:LaserPowderBedFusion rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?param ] .
  ?param rdfs:label ?label .
}
```
*Expected: LaserPowerParameter, ScanSpeed, LayerThickness, HatchSpacing, TrackOverlap, Wavelength*

---

**CQ6. What parameters are required for Spark Plasma Sintering?**
```sparql
SELECT ?param ?label WHERE {
  mds:SparkPlasmaSintering rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?param ] .
  ?param rdfs:label ?label .
}
```
*Expected: SinteringTemperature, SinteringPressure, PulsedCurrent*

---

**CQ7. Which processes require ShieldingGas as a parameter?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom mds:ShieldingGas ] .
  ?process rdfs:label ?label .
}
```
*Expected: WireArcAdditiveManufacturing, Welding*

---

**CQ8. Which processes require Wavelength as a parameter?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom mds:Wavelength ] .
  ?process rdfs:label ?label .
}
```
*Expected: LaserPowderBedFusion, PulsedLaserDeposition, UVCuring*

---

**CQ9. Which processes declare no processing parameters?**
```sparql
SELECT ?process ?label WHERE {
  ?process rdfs:subClassOf mds:MaterialsProcessing .
  ?process rdfs:label ?label .
  FILTER NOT EXISTS {
    ?process rdfs:subClassOf
      [ a owl:Restriction ;
        owl:onProperty mds:hasProcessingParameter ] .
  }
}
```
*Expected: Etching, FlameFusion, PressurelessSintering, LaserEngineeredNetShaping (inherits from DirectMetalDeposition)*

---

**CQ10. How many parameters does each process declare? (ranked)**
```sparql
SELECT ?process (COUNT(?param) AS ?numParams) WHERE {
  ?process rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?param ] .
}
GROUP BY ?process
ORDER BY DESC(?numParams)
```
*Expected: WireArcAdditiveManufacturing and PulsedLaserDeposition near top with 5 each*

---

## Parameter Hierarchy

**CQ11. What are all subtypes of ProcessingTemperature?**
```sparql
SELECT ?param ?label WHERE {
  ?param rdfs:subClassOf mds:ProcessingTemperature .
  ?param rdfs:label ?label .
}
ORDER BY ?label
```
*Expected: 11 classes — AgingTemperature, CuringTemperature, DepositionTemperature, ExtrusionTemperature, ForgingTemperature, HeadTemperature, MeltTemperature, PouringTemperature, QuenchingTemperature, ReactionTemperature, SinteringTemperature*

---

**CQ12. What are all subtypes of DwellTime?**
```sparql
SELECT ?param ?label WHERE {
  ?param rdfs:subClassOf mds:DwellTime .
  ?param rdfs:label ?label .
}
```
*Expected: AgingTime, CuringTime, GrowthTime, ProcessingTime*

---

**CQ13. What are all subtypes of ProcessingPressure?**
```sparql
SELECT ?param ?label WHERE {
  ?param rdfs:subClassOf mds:ProcessingPressure .
  ?param rdfs:label ?label .
}
```
*Expected: ForgingPressure, GasPressure, IsostaticPressure, ReactionPressure, SinteringPressure, SputterPressure, VacuumLevel*

---

## Units

**CQ14. What unit is associated with ScanSpeed?**
```sparql
SELECT ?unit WHERE {
  mds:ScanSpeed qudt:applicableUnit ?unit .
}
```
*Expected: unit:MilliM-PER-SEC*

---

**CQ15. Which parameters are measured in degrees Celsius?**
```sparql
SELECT ?param ?label WHERE {
  ?param qudt:applicableUnit unit:DEG_C .
  ?param rdfs:subClassOf+ mds:ProcessingParameter .
  ?param rdfs:label ?label .
}
ORDER BY ?label
```
*Expected: All ProcessingTemperature subtypes + ProcessingTemperature itself (11 classes)*

---

**CQ16. Which parameters have no unit declared?**
```sparql
SELECT ?param ?label WHERE {
  ?param rdfs:subClassOf+ mds:ProcessingParameter .
  ?param rdfs:label ?label .
  FILTER NOT EXISTS { ?param qudt:applicableUnit ?u . }
}
ORDER BY ?label
```
*Expected: BallMaterial, BuildDirection, CarrierGas, FeedstockComposition, FoilType, GasMetalRatio, Precursors, QuenchType, QuenchingMedia, ShieldingGas, SolutionType, Solvent, SolventFlux, TapeType*

---

## Standards & Provenance

**CQ17. Which processes cite an ISO or ASTM standard?**
```sparql
SELECT ?process ?label ?source WHERE {
  ?process rdfs:subClassOf+ mds:MaterialsProcessing .
  ?process rdfs:label ?label .
  ?process dcterms:source ?source .
}
ORDER BY ?label
```
*Expected: Annealing (ISO 4885:2018), Casting (ISO 8062-3:2007), Forging (ISO 7912:2013), HotIsostaticPressing (ASTM F2924-14), LPBF (ISO/ASTM 52900:2021, ASTM F2792-12a), MaterialsProcessing (ISO 9000:2015), PrecipitationHardening (ISO 4885:2018), Quenching (ISO 4885:2018), Sintering (ISO 3252:2019), SparkPlasmaSintering (ISO 18755:2020), WireArcAdditiveManufacturing (ISO/ASTM 52900:2021), etc.*

---

## Synonyms & Discovery

**CQ18. Which process is known by the abbreviation "SPS"?**
```sparql
SELECT ?process ?label WHERE {
  ?process skos:altLabel "SPS" .
  ?process rdfs:label ?label .
}
```
*Expected: mds:SparkPlasmaSintering — "Spark Plasma Sintering"*

---

**CQ19. Which process is known by the abbreviation "HEBM"?**
```sparql
SELECT ?process ?label WHERE {
  ?process skos:altLabel "HEBM" .
  ?process rdfs:label ?label .
}
```
*Expected: mds:BallMilling — "Ball Milling"*

---

## Cross-Process Queries

**CQ20. Which processes share both a temperature parameter and a pressure parameter?**
```sparql
SELECT DISTINCT ?process ?label WHERE {
  ?process rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?tempParam ] .
  ?tempParam rdfs:subClassOf+ mds:ProcessingTemperature .

  ?process rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty mds:hasProcessingParameter ;
      owl:someValuesFrom ?pressParam ] .
  ?pressParam rdfs:subClassOf+ mds:ProcessingPressure .

  ?process rdfs:label ?label .
}
ORDER BY ?label
```
*Expected: Forging, HotIsostaticPressing, HotPressing, SolvothermalProcessing, SparkPlasmaSintering*

---

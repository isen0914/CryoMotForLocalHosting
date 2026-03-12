# Clustering Algorithms Pseudocode

---

## ALGORITHM 1: Pseudocode of HDBSCAN Algorithm

**Input:** *DB*: Database  
**Input:** *minPts*: Minimum cluster size  
**Input:** *dist*: Distance function  
**Data:** *label*: Point labels, initially *undefined*  
**Data:** *core_dist*: Core distances for each point  
**Data:** *mreach_dist*: Mutual reachability distances  

```
1  foreach point p in database DB do                        // Compute core distances
2      Neighbors N ← RANGEQUERY(DB, dist, p, k)
3      core_dist(p) ← distance to kth nearest neighbor
4  
5  Create minimum spanning tree MST from mutual              // Build MST
6      reachability distances
7  
8  foreach edge (p, q) in MST do                             // Compute mutual reachability
9      mreach_dist(p, q) ← max(core_dist(p), 
10                             core_dist(q), dist(p, q))
11 
12 Sort edges in MST by mreach_dist                          // Sort by distance
13 
14 Build dendrogram hierarchy by removing edges              // Hierarchical clustering
15     from largest to smallest distance
16 
17 foreach cluster C in hierarchy do                         // Extract stable clusters
18     Compute stability score for C
19     if stability(C) > stability(children(C)) then
20         Extract C as a cluster
21     else
22         Extract children of C
23 
24 foreach point p in DB do                                  // Assign final labels
25     if p belongs to extracted cluster then
26         label(p) ← cluster_id
27     else
28         label(p) ← Noise
```

---

## ALGORITHM 2: Pseudocode of OPTICS Algorithm

**Input:** *DB*: Database  
**Input:** *ε*: Maximum radius  
**Input:** *minPts*: Density threshold  
**Input:** *dist*: Distance function  
**Data:** *reachability_dist*: Reachability distance, initially *undefined*  
**Data:** *core_dist*: Core distance for each point  
**Data:** *ordered_list*: Ordered list of points  

```
1  ordered_list ← empty list                                 // Initialize output
2  
3  foreach point p in database DB do                         // Process all points
4      if p is processed then continue                       // Skip processed points
5      
6      Neighbors N ← RANGEQUERY(DB, dist, p, ε)              // Find neighbors
7      
8      Mark p as processed
9      
10     ordered_list.append(p)                                 // Add to ordered list
11     
12     if |N| < minPts then                                   // Non-core points
13         core_dist(p) ← undefined
14         continue
15     
16     core_dist(p) ← distance to minPts-th neighbor          // Core distance
17     
18     Create priority queue Seeds with N \ {p}               // Initialize seeds
19     
20     foreach q in Seeds do                                  // Update reachability
21         new_reach_dist ← max(core_dist(p), dist(p, q))
22         if reachability_dist(q) = undefined then
23             reachability_dist(q) ← new_reach_dist
24             Seeds.update(q, new_reach_dist)
25         else if new_reach_dist < reachability_dist(q) then
26             reachability_dist(q) ← new_reach_dist
27             Seeds.update(q, new_reach_dist)
28     
29     while Seeds is not empty do                            // Expand cluster order
30         q ← Seeds.extractMin()
31         Neighbors N' ← RANGEQUERY(DB, dist, q, ε)
32         Mark q as processed
33         ordered_list.append(q)
34         
35         if |N'| ≥ minPts then                              // Core point expansion
36             core_dist(q) ← distance to minPts-th neighbor
37             foreach r in N' do
38                 if r is not processed then
39                     new_reach_dist ← max(core_dist(q), dist(q, r))
40                     if reachability_dist(r) = undefined then
41                         reachability_dist(r) ← new_reach_dist
42                         Seeds.insert(r, new_reach_dist)
43                     else if new_reach_dist < reachability_dist(r) then
44                         reachability_dist(r) ← new_reach_dist
45                         Seeds.update(r, new_reach_dist)
```

---

## ALGORITHM 3: Pseudocode of Minimum Spanning Tree (Prim's Algorithm)

**Input:** *G*: Graph with vertices V and edges E  
**Input:** *weight*: Edge weight function  
**Output:** *MST*: Minimum spanning tree  

```
1  MST ← empty set                                           // Initialize MST
2  visited ← empty set                                       // Track visited vertices
3  
4  v_start ← arbitrary vertex from V                         // Choose start vertex
5  visited.add(v_start)
6  
7  Create priority queue PQ with all edges from v_start      // Initialize with edges
8  
9  while |visited| < |V| and PQ is not empty do              // Build MST
10     
11     edge (u, v) ← PQ.extractMin()                         // Get minimum weight edge
12     
13     if v in visited then continue                          // Skip if already visited
14     
15     MST.add(edge (u, v))                                   // Add edge to MST
16     visited.add(v)                                         // Mark vertex as visited
17     
18     foreach edge (v, w) adjacent to v do                   // Add new edges
19         if w not in visited then
20             PQ.insert(edge (v, w), weight(v, w))
21 
22 return MST                                                 // Return spanning tree
```

---

## ALGORITHM 4: Pseudocode of Affinity Propagation (AFP)

**Input:** *S*: Similarity matrix (S(i, k) = similarity between points i and k)  
**Input:** *λ*: Damping factor (typically 0.5 to 1.0)  
**Input:** *max_iter*: Maximum iterations  
**Input:** *convergence*: Convergence criterion  
**Data:** *R*: Responsibility matrix, initially zeros  
**Data:** *A*: Availability matrix, initially zeros  

```
1  Initialize R(i, k) ← 0 for all i, k                       // Initialize responsibilities
2  Initialize A(i, k) ← 0 for all i, k                       // Initialize availabilities
3  
4  iter ← 0
5  
6  while iter < max_iter do                                   // Iterate until convergence
7      iter ← iter + 1
8      
9      R_old ← R                                              // Store old values
10     A_old ← A
11     
12     foreach i, k do                                        // Update responsibilities
13         R(i, k) ← S(i, k) - max{A(i, k') + S(i, k') 
14                             for all k' ≠ k}
15     
16     R ← λ × R_old + (1 - λ) × R                           // Apply damping
17     
18     foreach i, k do                                        // Update availabilities
19         if i = k then                                      // Self-availability
20             A(k, k) ← sum{max(0, R(i', k)) 
21                          for all i' ≠ k}
22         else                                               // Availability from k to i
23             A(i, k) ← min(0, R(k, k) + 
24                          sum{max(0, R(i', k)) 
25                              for all i' ∉ {i, k}})
26     
27     A ← λ × A_old + (1 - λ) × A                           // Apply damping
28     
29     exemplars ← {i : R(i, i) + A(i, i) > 0}               // Identify exemplars
30     
31     if exemplars converged for convergence iterations then // Check convergence
32         break
33 
34 foreach point i do                                         // Assign cluster labels
35     if i in exemplars then
36         label(i) ← i                                       // Point is exemplar
37     else
38         k* ← argmax{S(i, k) + R(i, k) + A(i, k)}          // Find best exemplar
39         label(i) ← k*
```

---

## Notes

- **HDBSCAN** extends DBSCAN by creating a hierarchy of clusters and extracting stable clusters based on their lifetime in the hierarchy.

- **OPTICS** creates a reachability plot that can be used to extract clusters at different density levels without re-running the algorithm.

- **MST (Prim's Algorithm)** builds a minimum spanning tree by greedily selecting the minimum weight edge that connects a visited vertex to an unvisited vertex.

- **AFP (Affinity Propagation)** finds exemplars by passing messages between data points about their suitability as exemplars until convergence.

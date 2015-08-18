# -*- coding: utf-8 -*-
"""
Created on Thu Feb 19 11:49:39 2015
@author: Ingo Scholtes, Roman Cattaneo

(c) Copyright ETH Zürich, Chair of Systems Design, 2015
"""

import numpy as np
import scipy.sparse as sparse
import scipy.sparse.linalg as sla

from collections import defaultdict
import sys

from bisect import bisect_left

from pyTempNet import Utilities
from pyTempNet import Paths

def Laplacian(temporalnet, model="SECOND"):
    """Returns the Laplacian matrix corresponding to the the second-order (model=SECOND) or 
    the second-order null (model=NULL) model for a temporal network.
    
    @param temporalnet: The temporalnetwork instance to work on
    @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value.
    """
    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")
    
    if model == "SECOND":
        network = temporalnet.igraphSecondOrder().components(mode="STRONG").giant()
    elif model == "NULL": 
        network = temporalnet.igraphSecondOrderNull().components(mode="STRONG").giant()  
    
    T2 = Utilities.RWTransitionMatrix( network )
    I  = sparse.identity( len(network.vs()) )

    return I-T2


def FiedlerVector(temporalnet, model="SECOND", lanczosVecs=15, maxiter=10):
    """Returns the Fiedler vector of the second-order (model=SECOND) or the
    second-order null (model=NULL) model for a temporal network. The Fiedler 
     vector can be used for a spectral bisectioning of the network.
     
    @param temporalnet: The temporalnetwork instance to work on
    @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value.
    @param lanczosVecs: number of Lanczos vectors to be used in the approximate
        calculation of eigenvectors and eigenvalues. This maps to the ncv parameter 
        of scipy's underlying function eigs. 
    @param maxiter: scaling factor for the number of iterations to be used in the 
        approximate calculation of eigenvectors and eigenvalues. The number of iterations 
        passed to scipy's underlying eigs function will be n*maxiter where n is the 
        number of rows/columns of the Laplacian matrix.
    """
    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")
    
    # NOTE: The transposed matrix is needed to get the "left" eigen vectors
    L = Laplacian(temporalnet, model)
    # NOTE: ncv=13 sets additional auxiliary eigenvectors that are computed
    # NOTE: in order to be more confident to find the one with the largest
    # NOTE: magnitude, see
    # NOTE: https://github.com/scipy/scipy/issues/4987
    maxiter = maxiter*L.get_shape()[0]

    import scipy.linalg as la

    w, v = la.eig(L.todense())
    # TODO: ask, if this vector should be normalized. Sparse Linalg sometimes
    # TODO: finds the EV scaled factor (-1)
    return v[:,np.argsort(np.absolute(w))][:,1]


def AlgebraicConn(temporalnet, model="SECOND"):
    """Returns the algebraic connectivity of the second-order (model=SECOND) or the
    second-order null (model=NULL) model for a temporal network.
    
     @param temporalnet: The temporalnetwork to work on
     @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value.
    """
    
    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")
    
    L = Laplacian(temporalnet, model)
    # NOTE: ncv=13 sets additional auxiliary eigenvectors that are computed
    # NOTE: in order to be more confident to find the one with the largest
    # NOTE: magnitude, see
    # NOTE: https://github.com/scipy/scipy/issues/4987
    w = sla.eigs( L, which="SM", k=2, ncv=13, return_eigenvectors=False )
    evals_sorted = np.sort(np.absolute(w))
    return np.abs(evals_sorted[1])
    
    
def EntropyGrowthRateRatio(t, mode='FIRSTORDER'):
    """Computes the ratio between the entropy growth rate ratio between
    the second-order and first-order model of a temporal network t. Ratios smaller
    than one indicate that the temporal network exhibits non-Markovian characteristics"""
    
    # NOTE to myself: most of the time here goes into computation of the
    # NOTE            EV of the transition matrix for the bigger of the
    # NOTE            two graphs below (either 2nd-order or 2nd-order null)
    
    # Generate strongly connected component of second-order networks
    g2 = t.igraphSecondOrder().components(mode="STRONG").giant()
    
    if mode == 'FIRSTORDER':
        g2n = t.igraphFirstOrder().components(mode="STRONG").giant()
    else:
        g2n = t.igraphSecondOrderNull().components(mode="STRONG").giant()
    
    # Calculate transition matrices
    T2 = Utilities.RWTransitionMatrix(g2)
    T2n = Utilities.RWTransitionMatrix(g2n)

    # Compute entropy growth rates of transition matrices        
    H2 = np.absolute(Utilities.EntropyGrowthRate(T2))
    H2n = np.absolute(Utilities.EntropyGrowthRate(T2n))

    # Return ratio
    return H2/H2n

def BetweennessPreferences(t, normalized=False):
    bwp = []
    for v in t.igraphFirstOrder().vs()["name"]:
        bwp.append(BetweennessPreference(t, v, normalized))
    return np.array(bwp)


def BetweennessPreference(t, v, normalized = False):
    """Computes the betweenness preference of a node v in a temporal network t
    
    @param t: The temporalnetwork instance to work on
    @param v: Name of the node to compute its BetweennessPreference
    @param normalized: whether or not (default) to normalize
    """
    g = t.igraphFirstOrder()
    
    # If the network is empty, just return zero
    if len(g.vs) == 0:
        return 0.0

    # First create the betweenness preference matrix (equation (2) of the paper)
    B_v = Utilities.BWPrefMatrix(t, v)
    
    # Normalize matrix (equation (3) of the paper)
    # NOTE: P_v has the same shape as B_v
    P_v = np.zeros(shape=B_v.shape)
    S = np.sum(B_v)
    
    if S>0:
        P_v = B_v / S

    ## Compute marginal probabilities
    ## Marginal probabilities P^v_d = \sum_s'{P_{s'd}}
    marginal_d = np.sum(P_v, axis=0)

    ## Marginal probabilities P^v_s = \sum_d'{P_{sd'}}
    marginal_s = np.sum(P_v, axis=1)
    
    H_s = Utilities.Entropy(marginal_s)
    H_d = Utilities.Entropy(marginal_d)
    
    # build mask for non-zero elements
    row, col = np.nonzero(P_v)
    pv = P_v[(row,col)]
    marginal = np.outer(marginal_s, marginal_d)
    log_argument = np.divide( pv, marginal[(row,col)] )
    
    I = np.dot( pv, np.log2(log_argument) )
    
    if normalized:
        I =  I/np.min([H_s,H_d])

    return I

def SlowDownFactor(t):    
    """Returns a factor S that indicates how much slower (S>1) or faster (S<1)
    a diffusion process in the temporal network evolves on a second-order model 
    compared to a first-order model. This value captures the effect of order
    correlations on a diffusion process in the temporal network.
    
    @param t: The temporalnetwork instance to work on
    """
    
    #NOTE to myself: most of the time goes for construction of the 2nd order
    #NOTE            null graph, then for the 2nd order null transition matrix
    
    g2 = t.igraphSecondOrder().components(mode="STRONG").giant()
    g2n = t.igraphSecondOrderNull().components(mode="STRONG").giant()
    
    # Build transition matrices
    T2 = Utilities.RWTransitionMatrix(g2)
    T2n = Utilities.RWTransitionMatrix(g2n)
    
    # Compute eigenvector sequences
    # NOTE: ncv=13 sets additional auxiliary eigenvectors that are computed
    # NOTE: in order to be more confident to find the one with the largest
    # NOTE: magnitude, see
    # NOTE: https://github.com/scipy/scipy/issues/4987
    w2 = sla.eigs(T2, which="LM", k=2, ncv=13, return_eigenvectors=False)
    evals2_sorted = np.sort(-np.absolute(w2))

    w2n = sla.eigs(T2n, which="LM", k=2, ncv=13, return_eigenvectors=False)
    evals2n_sorted = np.sort(-np.absolute(w2n))
    
    return np.log(np.abs(evals2n_sorted[1]))/np.log(np.abs(evals2_sorted[1]))


def GetStaticEigenvectorCentrality(t, model='SECOND'):
    """Computes eigenvector centralities of nodes in the second-order aggregate network, 
    and aggregates eigenvector centralities to obtain the eigenvector centrality of nodes in the 
    first-order network.
    
    @param t: The temporalnetwork instance to work on
    @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value."""

    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")

    name_map = Utilities.firstOrderNameMap(t)
    
    if model == 'SECOND':
        g2 = t.igraphSecondOrder()
    else:
        g2 = t.igraphSecondOrderNull()
    
    # Compute eigenvector centrality in second-order network
    A = Utilities.getSparseAdjacencyMatrix( g2, attribute="weight", transposed=True )
    evcent_2 = Utilities.StationaryDistribution( A, False )
    
    # Aggregate to obtain first-order eigenvector centrality
    evcent_1 = np.zeros(len(name_map))
    sep = t.separator
    for i in range(len(evcent_2)):
        # Get name of target node
        target = g2.vs()[i]["name"].split(sep)[1]
        evcent_1[name_map[target]] += np.real(evcent_2[i])
    
    return np.real(evcent_1/sum(evcent_1))


def GetStaticPageRank(t, model='SECOND'):
    """Computes PageRank of nodes based on the second-order aggregate network, 
    and aggregates PageRank values to obtain the PageRank of nodes in the
    first-order network.
    
    @param t: The temporalnetwork instance to work on
    @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value.
    """

    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")

    name_map = Utilities.firstOrderNameMap( t )

    if model == 'SECOND':
        g2 = t.igraphSecondOrder()
    else:
        g2 = t.igraphSecondOrderNull()    

    # Compute betweenness centrality in second-order network
    pagerank_2 = np.array(g2.pagerank(weights=g2.es()['weight'], directed=True))
    
    # Aggregate to obtain first-order eigenvector centrality
    pagerank_1 = np.zeros(len(name_map))
    sep = t.separator
    for i in range(len(pagerank_2)):
        # Get name of target node
        target = g2.vs()[i]["name"].split(sep)[1]
        pagerank_1[name_map[target]] += pagerank_2[i]
    
    return pagerank_1/sum(pagerank_1)



def GetStaticBetweenness(t, model='SECOND'):
    """Computes betweenness centralities of nodes based on the second-order aggregate network, 
    and aggregates betweenness centralities to obtain the betweenness centrality of nodes in the 
    first-order network.
    
    @param t: The temporalnetwork instance to work on
    @param model: either C{"SECOND"} or C{"NULL"}, where C{"SECOND"} is the 
      the default value.
    """

    if (model is "SECOND" or "NULL") == False:
        raise ValueError("model must be one of \"SECOND\" or \"NULL\"")

    D = Paths.GetSecondOrderDistanceMatrix(t)
    name_map = Utilities.firstOrderNameMap( t )

    if model == 'SECOND':
        g2 = t.igraphSecondOrder()
    else:
        g2 = t.igraphSecondOrderNull()

    # Compute betweenness centrality based on second-order network
    bwcent_1 = np.zeros(len(name_map))
    sep = t.separator

    for v in g2.vs()["name"]:
        for w in g2.vs()["name"]:
            s = v.split(sep)[0]
            t = w.split(sep)[1]
            X = g2.get_all_shortest_paths(v,w)
            for p in X:
                if D[name_map[s], name_map[t]] == len(p) and len(p) > 1:
                    for i in range(len(p)):
                        source = g2.vs()["name"][p[i]].split(sep)[0]
                        if i>0:
                            bwcent_1[name_map[source]] += 1
    
    return bwcent_1


def GetTemporalBetweenness(t, delta=1, normalized=False):
    """Calculates the temporal betweenness centralities of all nodes 
    in a temporal network t based on the shortest time-respecting paths with a 
    maximum waiting time of delta. This function returns a numpy array of temporal betweenness centrality values of 
    nodes. The ordering of these values corresponds to the ordering of nodes in the vertex sequence 
    of the igraph first order time-aggregated network. A mapping between node names and array 
    indices can be found in  Utilities.firstOrderNameMap().
    
    @param t: the temporal network for which temporal closeness centralities will be computed    
    @param delta: the maximum time difference used in the time-respecting path definition (default 1).
        Note that this parameter is independent from the delta used internally for the extraction of two-paths
        by the class TemporalNetwork
    @param normalized: whether or not to normalize centralities by dividing each value byt the total number 
        of shortest time-respecting paths.
    """

    bw = np.array([0]*len(t.nodes))
    S = 0

    name_map = Utilities.firstOrderNameMap(t)

    minD, minPaths = Paths.GetMinTemporalDistance(t, delta=1, collect_paths=True)

    for v in t.nodes:
        for w in t.nodes:
            for p in minPaths[v][w]:
                for i in range(1,len(p)-1):
                    bw[name_map[p[i]]] += 1
                    S+=1
    return bw


def GetTemporalBetweennessInstantaneous(t, start_t=0, delta=1, normalized=False):
    """Calculates the temporal betweennness values of 
    all nodes fir a given start time start_t in an empirical temporal network t.
    This function returns a numpy array of (temporal) betweenness centrality values. 
    The ordering of these values corresponds to the ordering of nodes in the vertex 
    sequence of the igraph first order time-aggregated network. A mapping between node names
    and array indices can be found in Utilities.firstOrderNameMap().
    
    @param t: the temporal network for which temporal betweenness centralities will be computed
    @param start_t: the start time for which to consider time-respecting paths (default 0). This is 
        important, since any unambigious definition of a shortest time-respecting path between
        two nodes must include the time range to be considered (c.f. Holme and Saramäki, Phys. Rep., 2012)
    @param delta: the maximum waiting time used in the time-respecting path definition (default 1)
        Note that this parameter is independent from the delta used internally for the extraction of two-paths
        by the class TemporalNetwork
    @param normalized: whether or not to normalize the temporal betweenness centrality values by
    dividing by the number of all shortest time-respecting paths in the temporal network.
    """

    bw = np.array([0]*len(t.nodes))

    # First calculate all shortest time-respecting paths starting at time start_t
    D, paths = Paths.GetTemporalDistanceMatrix(t, start_t, delta)

    # Get a mapping between node names and matrix indices
    name_map = Utilities.firstOrderNameMap( t )

    # Compute betweenness scores of all nodes based on shortest time-respecting paths
    k=0
    for u in t.nodes:
        for v in t.nodes:
            if u != v:
                for p in paths[u][v]:
                    for i in range(1, len(p)-1):
                        bw[name_map[p[i]]] += 1
                        k+=1

    # Normalize by dividing by the total number of shortest time-respecting paths
    if normalized:
        bw = bw/k
    return bw


def GetStaticCloseness(t, model='SECOND'):
    """Computes closeness centralities of nodes based on the first- or second-order time-aggregated network.
    
    @param t: The temporal network instance for which closeness centralities will be computed
    @param model: either C{"FIRST"}, C{"SECOND"} or C{"SECONDNULL"}, where C{"SECOND"} is the 
      the default value.
    """

    if model =='FIRST':
        D = Paths.GetFirstOrderDistanceMatrix(t)
    else:
        D = Paths.GetSecondOrderDistanceMatrix(t, model)

    name_map = Utilities.firstOrderNameMap( t )

    closeness = np.zeros(len(name_map))

    # Calculate closeness for each node u, by summing the reciprocal of its 
    # distances to all other nodes. Note that this definition of closeness centrality 
    # is required for directed networks that are not strongly connected. 
    for u in t.nodes:
        for v in t.nodes:
            if u!=v:
                closeness[name_map[u]] += 1./D[name_map[v], name_map[u]]
    
    return closeness


def GetTemporalCloseness(t, delta=1):
    """Calculates the temporal closeness centralities of all nodes 
    in a temporal network t, based on the minimal shortest time-respecting paths with a 
    maximum time difference of delta. This function then returns a numpy 
    array of average (temporal) closeness centrality values of nodes. The ordering of these 
    values corresponds to the ordering of nodes in the vertex sequence of the igraph first order 
    time-aggregated network. A mapping between node names and array indices can be found in 
    Utilities.firstOrderNameMap().
    
    @param t: the temporal network for which temporal closeness centralities will be computed    
    @param delta: the maximum waiting time used in the time-respecting path definition (default 1)      
        Note that this parameter is independent from the delta used internally for the extraction of two-paths
        by the class TemporalNetwork     
    """

    cl = np.array([0.]*len(t.nodes))

    name_map = Utilities.firstOrderNameMap( t )

    minD, minPaths = Paths.GetMinTemporalDistance(t, delta, True)

    for u in t.nodes:
        for v in t.nodes:
            if u!= v:
                cl[name_map[v]] += 1./minD[name_map[u], name_map[v]]
    return cl


def GetTemporalClosenessInstantaneous(t, start_t=0, delta=1):
    """Calculates the temporal closeness values of 
    all nodes for a given start time start_t in a temporal network t.
    This function returns a numpy array of (temporal) closeness centrality values. 
    The ordering of these values corresponds to the ordering of nodes in the vertex 
    sequence of the igraph first order time-aggregated network. A mapping between node names
    and array indices can be found in Utilities.firstOrderNameMap().
    
    @param t: the temporal network for which temporal closeness centralities will be computed
    @param start_t: the start time for which to consider time-respecting paths (default 0). This is 
        important, since any unambigious definition of a shortest time-respecting path between
        two nodes must include the time range to be considered (c.f. Holme and Saramäki, Phys. Rep., 2012)
    @param delta: the maximum time difference time used in the time-respecting path definition (default 1)
        Note that this parameter is independent from the delta used internally for the extraction of two-paths
        by the class TemporalNetwork.
    """
    
    closeness = np.array([0.]*len(t.nodes))

    # Calculate all shortest time-respecting paths
    D, paths = Paths.GetTemporalDistanceMatrix(t, start_t, delta)    

    # Get a mapping between node names and matrix indices
    name_map = Utilities.firstOrderNameMap( t )

    # Calculate closeness for each node u, by summing the reciprocal of its 
    # distances to all other nodes. Note that this definition of closeness centrality 
    # is required for directed networks that are not strongly connected. 
    for u in t.nodes:
        for v in t.nodes:
            if u!=v:
                closeness[name_map[u]] += 1./D[name_map[v], name_map[u]]

    return closeness
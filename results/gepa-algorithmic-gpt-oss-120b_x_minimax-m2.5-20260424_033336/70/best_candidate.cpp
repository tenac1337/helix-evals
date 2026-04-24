#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    int t;
    if (!(cin >> t)) return 0;
    
    for (int case_num = 0; case_num < t; ++case_num) {
        int n, m, start, base_move_count;
        cin >> n >> m >> start >> base_move_count;
        
        // Read and discard edges
        for (int i = 0; i < m; ++i) {
            int u, v;
            cin >> u >> v;
        }
        
        // Track previous vertex degree to avoid immediate backtracking
        int prev_degree = -1;
        
        while (true) {
            string token;
            if (!(cin >> token)) break;
            
            if (token == "AC" || token == "F") {
                break;
            }
            
            int d = stoi(token);
            
            vector<int> neighbor_degrees;
            vector<int> neighbor_flags;
            
            for (int i = 0; i < d; ++i) {
                int deg, flag;
                cin >> deg >> flag;
                neighbor_degrees.push_back(deg);
                neighbor_flags.push_back(flag);
            }
            
            // Strategy: 
            // 1. If there are unvisited neighbors (flag=0), pick one with LOWEST degree
            //    (leaves/dead-ends first - reduces backtracking)
            // 2. If all neighbors visited (flag=1):
            //    a) First try to avoid going back to the vertex we just came from
            //       (if prev_degree matches a neighbor, and there are other options)
            //    b) Among remaining visited neighbors, pick HIGHEST degree
            //       (more connections = more likely to reach unvisited areas)
            
            int choice = 1;
            
            // Check for unvisited neighbors
            bool has_unvisited = false;
            for (int flag : neighbor_flags) {
                if (flag == 0) {
                    has_unvisited = true;
                    break;
                }
            }
            
            if (has_unvisited) {
                // Find unvisited neighbor with minimum degree
                int best_idx = -1;
                int min_deg = INT_MAX;
                for (int i = 0; i < d; ++i) {
                    if (neighbor_flags[i] == 0 && neighbor_degrees[i] < min_deg) {
                        min_deg = neighbor_degrees[i];
                        best_idx = i;
                    }
                }
                choice = best_idx + 1;
            } else {
                // All neighbors visited - need smarter selection
                // First, identify if prev_degree is among neighbors
                int prev_idx = -1;
                if (prev_degree != -1) {
                    for (int i = 0; i < d; ++i) {
                        if (neighbor_degrees[i] == prev_degree) {
                            prev_idx = i;
                            break;
                        }
                    }
                }
                
                // Count how many neighbors have the maximum degree
                int max_deg = neighbor_degrees[0];
                for (int i = 1; i < d; ++i) {
                    if (neighbor_degrees[i] > max_deg) {
                        max_deg = neighbor_degrees[i];
                    }
                }
                
                // Find best index: prefer highest degree, but avoid prev if possible
                // and if there are multiple with max degree, pick one that's not prev
                int best_idx = 0;
                bool found_non_prev_max = false;
                
                // First pass: look for max degree that's not prev
                for (int i = 0; i < d; ++i) {
                    if (neighbor_degrees[i] == max_deg && i != prev_idx) {
                        best_idx = i;
                        found_non_prev_max = true;
                        break;
                    }
                }
                
                // If we couldn't find a non-prev max, just use the first max degree
                if (!found_non_prev_max) {
                    for (int i = 0; i < d; ++i) {
                        if (neighbor_degrees[i] == max_deg) {
                            best_idx = i;
                            break;
                        }
                    }
                }
                
                choice = best_idx + 1;
            }
            
            // Update prev_degree for next iteration (current vertex degree)
            prev_degree = d;
            
            cout << choice << "\n" << flush;
        }
    }
    
    return 0;
}
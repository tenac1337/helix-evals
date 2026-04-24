#include <bits/stdc++.h>
using namespace std;

// Structure to represent a polyomino
struct Polyomino {
    vector<pair<int, int>> cells;
    int id;
};

// Function to generate all rotations and reflections of a polyomino
vector<vector<pair<int, int>>> generateTransformations(const vector<pair<int, int>>& cells) {
    vector<vector<pair<int, int>>> transformations;
    
    // 4 rotations + 4 reflections = 8 total transformations
    for (int i = 0; i < 4; ++i) {
        vector<pair<int, int>> rotated = cells;
        for (auto& p : rotated) {
            if (i == 1) swap(p.first, p.second), p.second = -p.second;
            if (i == 2) p.first = -p.first, p.second = -p.second;
            if (i == 3) swap(p.first, p.second), p.first = -p.first;
        }
        transformations.push_back(rotated);
    }
    
    for (int i = 0; i < 4; ++i) {
        vector<pair<int, int>> reflected = cells;
        for (auto& p : reflected) {
            p.first = -p.first;
        }
        if (i == 1) swap(reflected[0].first, reflected[0].second), reflected[0].second = -reflected[0].second;
        if (i == 2) reflected[0].first = -reflected[0].first, reflected[0].second = -reflected[0].second;
        if (i == 3) swap(reflected[0].first, reflected[0].second), reflected[0].first = -reflected[0].first;
        transformations.push_back(reflected);
    }
    
    return transformations;
}

// Function to find bounding box of a polyomino
pair<pair<int, int>, pair<int, int>> getBoundingBox(const vector<pair<int, int>>& cells) {
    int minX = INT_MAX, maxX = INT_MIN;
    int minY = INT_MAX, maxY = INT_MIN;
    
    for (const auto& p : cells) {
        minX = min(minX, p.first);
        maxX = max(maxX, p.first);
        minY = min(minY, p.second);
        maxY = max(maxY, p.second);
    }
    
    return {{minX, minY}, {maxX, maxY}};
}

// Function to check if two polyominoes overlap
bool overlaps(const vector<pair<int, int>>& cells1, const vector<pair<int, int>>& cells2,
              int x1, int y1, int x2, int y2) {
    set<pair<int, int>> s1, s2;
    for (const auto& p : cells1) {
        s1.insert({p.first + x1, p.second + y1});
    }
    for (const auto& p : cells2) {
        s2.insert({p.first + x2, p.second + y2});
    }
    
    for (const auto& p : s1) {
        if (s2.count(p)) return true;
    }
    return false;
}

// Function to check if a polyomino fits in a given rectangle
bool fitsIn(const vector<pair<int, int>>& cells, int width, int height, int x, int y) {
    for (const auto& p : cells) {
        int newX = p.first + x;
        int newY = p.second + y;
        if (newX < 0 || newX >= width || newY < 0 || newY >= height) {
            return false;
        }
    }
    return true;
}

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    int n;
    cin >> n;
    vector<Polyomino> pieces(n);
    
    for (int i = 0; i < n; ++i) {
        int k;
        cin >> k;
        pieces[i].cells.resize(k);
        for (int j = 0; j < k; ++j) {
            cin >> pieces[i].cells[j].first >> pieces[i].cells[j].second;
        }
        pieces[i].id = i;
    }
    
    // Precompute all transformations for each piece
    vector<vector<vector<pair<int, int>>>> allTransforms(n);
    for (int i = 0; i < n; ++i) {
        allTransforms[i] = generateTransformations(pieces[i].cells);
    }
    
    // Simple greedy placement algorithm
    vector<vector<pair<int, int>>> placements(n);
    vector<pair<int, int>> positions(n);
    vector<int> rotations(n);
    vector<bool> reflected(n);
    vector<bool> placed(n, false);
    
    int totalArea = 0;
    for (int i = 0; i < n; ++i) {
        totalArea += pieces[i].cells.size();
    }
    
    // Initial estimate of area
    int minArea = totalArea;
    int width = ceil(sqrt(minArea));
    int height = width;
    
    // Try different sizes
    while (true) {
        vector<vector<bool>> grid(width, vector<bool>(height, false));
        vector<pair<int, int>> pos(n, {0, 0});
        vector<int> rot(n, 0);
        vector<bool> ref(n, false);
        vector<bool> placed(n, false);
        
        bool success = true;
        for (int i = 0; i < n; ++i) {
            bool found = false;
            for (int r = 0; r < 4; ++r) {
                for (int f = 0; f < 2; ++f) {
                    auto& trans = allTransforms[i][r + (f ? 4 : 0)];
                    pair<pair<int, int>, pair<int, int>> bb = getBoundingBox(trans);
                    int w = bb.second.first - bb.first.first;
                    int h = bb.second.second - bb.first.second;
                    
                    for (int x = 0; x <= width - w; ++x) {
                        for (int y = 0; y <= height - h; ++y) {
                            bool valid = true;
                            for (const auto& p : trans) {
                                int newX = p.first + x;
                                int newY = p.second + y;
                                if (newX < 0 || newX >= width || newY < 0 || newY >= height) {
                                    valid = false;
                                    break;
                                }
                                if (grid[newX][newY]) {
                                    valid = false;
                                    break;
                                }
                            }
                            
                            if (valid) {
                                for (const auto& p : trans) {
                                    int newX = p.first + x;
                                    int newY = p.second + y;
                                    grid[newX][newY] = true;
                                }
                                pos[i] = {x, y};
                                rot[i] = r;
                                ref[i] = f;
                                placed[i] = true;
                                found = true;
                                break;
                            }
                        }
                        if (found) break;
                    }
                    if (found) break;
                }
                if (found) break;
            }
            
            if (!found) {
                success = false;
                break;
            }
        }
        
        if (success) {
            cout << width << " " << height << "\n";
            for (int i = 0; i < n; ++i) {
                cout << pos[i].first << " " << pos[i].second << " " << rot[i] << " " << ref[i] << "\n";
            }
            return 0;
        }
        
        // Increase size
        if (width * height < 2 * totalArea) {
            width++;
            if (width * height >= 2 * totalArea) {
                height++;
                width = (int)ceil(sqrt(width * height));
            }
        } else {
            width++;
            height++;
        }
    }
    
    return 0;
}
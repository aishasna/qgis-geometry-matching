from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFile,
    QgsProcessing,
    QgsFeatureSink,
    QgsProcessingException,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsSpatialIndex,
    QgsGeometry,
    QgsWkbTypes 
)
from qgis.PyQt.QtCore import QVariant
from collections import defaultdict, Counter

class GeometryMatching(QgsProcessingAlgorithm):

    INPUT_DATASET_A = 'INPUT_DATASET_A'
    INPUT_DATASET_B = 'INPUT_DATASET_B'
    THR_OVERLAP = 'THR_OVERLAP' 
    OUTPUT_DATASET_A = 'OUTPUT_DATASET_A'
    OUTPUT_DATASET_B = 'OUTPUT_DATASET_B'
    OUTPUT_STATS = 'OUTPUT_STATS' 

    LIKELY_A_ID = ["ID", "FID", "PARCEL_ID", "PARCELID", "UID", "KEY"]
    LIKELY_B_ID = ["ID", "OBJECTID", "TARGET_ID", "TARGETID", "FID", "GUID"]

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(self.INPUT_DATASET_A, 'Layer A', [QgsProcessing.TypeVectorPolygon])
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(self.INPUT_DATASET_B, 'Layer B', [QgsProcessing.TypeVectorPolygon])
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.THR_OVERLAP, 
                'Overlap Threshold (e.g., 0.70)', 
                QgsProcessingParameterNumber.Double,
                defaultValue=0.70, 
                minValue=0.50,
                maxValue=1.0
            )
        )
        
        # Geometry Output
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT_DATASET_A, 'Dataset A Output (Geometry)', QgsProcessing.TypeVectorPolygon)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT_DATASET_B, 'Dataset B Output (Geometry)', QgsProcessing.TypeVectorPolygon)
        )
        
        # Statistics Output (Non-Geometrics)
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STATS, 
                'Output Summary Statistics (CSV/TXT)', 
                QgsProcessing.TypeFile,
                'Output Summary Statistics' 
            )
        )

    def area(self, g):
        return g.area() if g and not g.isEmpty() else 0.0

    def guess_id_field(self, layer, candidates):
        names = [f.name() for f in layer.fields()]
        for c in candidates:
            for n in names:
                if n.lower() == c.lower():
                    return n
        return names[0] if names else None
    
    def processAlgorithm(self, parameters, context, feedback):
        DatasetA_layer = self.parameterAsSource(parameters, self.INPUT_DATASET_A, context)
        DatasetB_layer = self.parameterAsSource(parameters, self.INPUT_DATASET_B, context)
        threshold = self.parameterAsDouble(parameters, self.THR_OVERLAP, context) 
        
        if DatasetA_layer is None or DatasetB_layer is None:
            raise QgsProcessingException('Layer Input tidak valid.')

        # 1. Parameter Initialization
        thr_percent = int(threshold * 100)
        
        feedback.pushInfo(f"Overlap Threshold = {thr_percent}%")

        A_id_field = self.guess_id_field(DatasetA_layer, self.LIKELY_A_ID)
        B_id_field = self.guess_id_field(DatasetB_layer, self.LIKELY_B_ID)
        total_A_features = DatasetA_layer.featureCount()
        total_B_features = DatasetB_layer.featureCount()
        
        #  (Core Logic: Indexing, Edge Calculation, Relationship Degrees, and Classification)
        A_index, A_feats = QgsSpatialIndex(), {}
        for fb in DatasetA_layer.getFeatures():
            A_feats[fb.id()] = (fb.geometry(), fb[A_id_field], self.area(fb.geometry()))
            A_index.insertFeature(fb)
        
        edges = []
        B_feats = {}
        for fs in DatasetB_layer.getFeatures():
             B_feats[fs.id()] = (fs.geometry(), fs[B_id_field], self.area(fs.geometry()))

        for i, (B_fid, (gs, pid, a_s)) in enumerate(B_feats.items()):
            if feedback.isCanceled(): return {}
            if a_s <= 0: continue
            
            bbox_ids = A_index.intersects(gs.boundingBox())
            
            for A_fid in bbox_ids:
                gb, bid, a_b = A_feats[A_fid] 
                if a_b <= 0: continue
                
                inter = gs.intersection(gb)
                a_int = self.area(inter)
                
                if a_int > 0: 
                    r_b = a_int / a_s  
                    r_a = a_int / a_b  
                    
                    edges.append({
                        "B_ID": pid, "A_ID": bid,
                        "R_B": r_b, "R_A": r_a
                    })
            feedback.setProgress(int(i * 50 / total_B_features))

        partners_a_by_b = defaultdict(set)
        partners_b_by_a = defaultdict(set)
        
        for e in edges:
            is_relevant = (e["R_B"] >= thr_percent) or (e["R_A"] >= thr_percent)
            
            if is_relevant:
                partners_a_by_b[e["B_ID"]].add(e["A_ID"])
                partners_b_by_a[e["A_ID"]].add(e["B_ID"])

        for e in edges:
            pid, bid = e["B_ID"], e["A_ID"]
            e["deg_b"] = len(partners_a_by_b[pid])
            e["deg_a"] = len(partners_b_by_a[bid])

        status_parcel_a, status_parcel_b = {}, {}
        # PASS 1: Relationship 1:1 (STRONG MATCH ^_^)
        for e in edges:
            pid, bid = e["B_ID"], e["A_ID"]
            if bid in status_parcel_a or pid in status_parcel_b: continue
            is_strong = (e["R_B"] >= thr_percent) and (e["R_A"] >= thr_percent)
            is_1_1_deg = (e["deg_b"] == 1) and (e["deg_a"] == 1) 
            if is_strong and is_1_1_deg:
                status_parcel_a[bid] = "1:1"
                status_parcel_b[pid] = "1:1"

        # PASS 2: 1:M (Split B) dan M:1 (Merge A)
        for e in edges:
            pid, bid = e["B_ID"], e["A_ID"]
            if status_parcel_a.get(bid) == "1:1" or status_parcel_b.get(pid) == "1:1": continue
            is_split_pbb_deg = (e["deg_a"] == 1) and (e["deg_b"] > 1)
            is_split_pbb_thr = (e["R_A"] >= thr_percent)
            if is_split_pbb_deg and is_split_pbb_thr:
                if bid not in status_parcel_a: status_parcel_a[bid] = "1:M (Split Parcel B)"
                if pid not in status_parcel_b: status_parcel_b[pid] = "1:M (Split Parcel B)"
                continue 
        for e in edges:
            pid, bid = e["B_ID"], e["A_ID"]
            if status_parcel_a.get(bid) == "1:1" or status_parcel_b.get(pid) == "1:1": continue
            if status_parcel_a.get(bid) == "1:M (Split Parcel B)" or status_parcel_b.get(pid) == "1:M (Split Parcel B)": continue
            is_merge_bpn_deg = (e["deg_a"] > 1) and (e["deg_b"] == 1)
            is_merge_bpn_thr = (e["R_B"] >= thr_percent)
            if is_merge_bpn_deg and is_merge_bpn_thr:
                if bid not in status_parcel_a: status_parcel_a[bid] = "M:1 (Merge Parcel A)"
                if pid not in status_parcel_b: status_parcel_b[pid] = "M:1 (Merge Parcel A)"
                continue

        # PASS 3: Need Review
        for e in edges:
            pid, bid = e["B_ID"], e["A_ID"]
            if bid not in status_parcel_a: status_parcel_a[bid] = "Need Review"
            if pid not in status_parcel_b: status_parcel_b[pid] = "Need Review"

        # 6. Calculation of Summary Statistics
        count_bpn = Counter(status_parcel_a.values())
        count_pbb = Counter(status_parcel_b.values())
        count_bpn["No Match"] = total_A_features - len(status_parcel_a)
        count_pbb["No Match"] = total_B_features - len(status_parcel_b)
        
        # 7. Writing Outputs (3 Output Sinks)
        
        # --- A. Sink Dataset A (Geometri) ---
        A_fields = DatasetA_layer.fields()
        A_fields.append(QgsField("STATUS", QVariant.String, "string", 50))
        (A_sink, A_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_DATASET_A, context, A_fields, 
            DatasetA_layer.wkbType(), DatasetA_layer.sourceCrs()
        )
        for f in DatasetA_layer.getFeatures():
            if feedback.isCanceled(): return {}
            new_feat = QgsFeature(A_fields)
            new_feat.setGeometry(f.geometry())
            current_status = status_parcel_a.get(f[A_id_field], "No Match")
            attrs = list(f.attributes())
            attrs.append(current_status)
            new_feat.setAttributes(attrs)
            A_sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            
        # --- B. Sink Dataset B (Geometri) ---
        B_fields = DatasetB_layer.fields()
        B_fields.append(QgsField("STATUS", QVariant.String, "string", 50))
        (B_sink, B_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_DATASET_B, context, B_fields, 
            DatasetB_layer.wkbType(), DatasetB_layer.sourceCrs()
        )
        for f in DatasetB_layer.getFeatures():
            if feedback.isCanceled(): return {}
            new_feat = QgsFeature(B_fields)
            new_feat.setGeometry(f.geometry())
            current_status = status_parcel_b.get(f[B_id_field], "No Match")
            attrs = list(f.attributes())
            attrs.append(current_status)
            new_feat.setAttributes(attrs)
            B_sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            
        # --- C. Summary Statistics Sink (Non-Geometric Table) ---
        stat_fields = QgsFields()
        stat_fields.append(QgsField("Match Threshold", QVariant.Int))
        stat_fields.append(QgsField("Layer name", QVariant.String))
        stat_fields.append(QgsField("Classification", QVariant.String))
        stat_fields.append(QgsField("Feature Count", QVariant.Int))
        stat_fields.append(QgsField("Percentage (%)", QVariant.Double))
        stat_fields.append(QgsField("Total Parcels", QVariant.Int))

        # NO SINK NAME REQUIRED, as this must be saved to a file by the user
        (stat_sink, stat_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_STATS, context, stat_fields, 
            QgsWkbTypes.NoGeometry, 
            DatasetA_layer.sourceCrs() 
        )
        
        def write_stats(layer_name, total, counts):
            for status, count in counts.items():
                percent = (count / total * 100) if total > 0 else 0.0
                feat = QgsFeature(stat_fields)
                feat.setAttributes([thr_percent, layer_name, status, count, percent, total])
                stat_sink.addFeature(feat, QgsFeatureSink.FastInsert)

        write_stats("Dataset A", total_A_features, count_bpn)
        write_stats("Dataset B", total_B_features, count_pbb)

        # 8. Final Return
        feedback.pushInfo(f"Analisis Selesai. Hasil statistik telah disimpan di layer Tabel Statistik Perbandingan (THR={thr_percent}%)")
        
        return {
            self.OUTPUT_DATASET_A: A_dest_id, 
            self.OUTPUT_DATASET_B: B_dest_id,
            self.OUTPUT_STATS: stat_dest_id
        }

    def name(self):
        return 'Geometry Matching'

    def displayName(self):
        return 'Automated Geometry Matching Tool'

    def group(self):
        return 'Custom Scripts'

    def groupId(self):
        return 'customscripts'

    def createInstance(self):
        return GeometryMatching()
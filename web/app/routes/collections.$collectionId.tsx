import { CollectionEditor } from "@/components/collection-editor";
import { useParams } from "@/hooks/use-router";
export default function EditCollection() {
  const { collectionId } = useParams<{ collectionId: string }>();
  return <CollectionEditor collectionId={collectionId} />;
}

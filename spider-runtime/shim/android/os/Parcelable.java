package android.os;

public interface Parcelable {

    public interface Creator {
        public Object createFromParcel(android.os.Parcel p);
        public Object[] newArray(int size);
    }
}
